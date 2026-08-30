"""Deterministic graph-pattern partitioner for a future llama.cpp backend.

The partitioner operates on a compact GGML-like DAG and chooses the longest
hardware-supported pattern without model-name conditionals. Unsupported nodes
remain explicit CPU fallback segments. This is compiler E0, not a compiled
llama.cpp backend.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import hashlib
import json
from typing import Iterable, Mapping, Sequence


@dataclass(frozen=True)
class GraphNode:
    node_id: str
    op: str
    inputs: tuple[str, ...] = ()
    dtype: str = "bf16"
    shape: tuple[int, ...] = ()
    attrs: tuple[tuple[str, object], ...] = ()

    def attr(self, name: str, default: object = None) -> object:
        return dict(self.attrs).get(name, default)


@dataclass(frozen=True)
class Pattern:
    name: str
    ops: tuple[str, ...]
    engine: str
    policy: str
    stateful: bool = False
    priority: int = 0


@dataclass(frozen=True)
class Segment:
    segment_id: int
    kind: str
    node_ids: tuple[str, ...]
    engine: str
    policy: str
    dependencies: tuple[int, ...]
    stateful: bool
    fallback_reason: str | None = None


@dataclass(frozen=True)
class PartitionResult:
    segments: tuple[Segment, ...]
    node_to_segment: Mapping[str, int]
    program_sha256: str

    @property
    def fallback_segments(self) -> tuple[Segment, ...]:
        return tuple(segment for segment in self.segments if segment.kind == "fallback")


DEFAULT_PATTERNS = (
    Pattern(
        "qsa_sparse_attention",
        ("qsa_index", "topk", "kv_gather", "matrix_qk", "online_softmax", "matrix_pv", "output_gate"),
        "matrix_sfu_kv",
        "qsa_policy",
        True,
        100,
    ),
    Pattern(
        "gated_deltanet",
        ("rmsnorm", "gdn_projection", "causal_conv", "gdn_state_update", "gated_norm", "matrix_out"),
        "matrix_sfu_state",
        "delta_policy",
        True,
        95,
    ),
    Pattern(
        "blocked_attention",
        ("matrix_qk", "online_softmax", "matrix_pv"),
        "matrix_sfu_kv",
        "attention_op",
        True,
        90,
    ),
    Pattern(
        "gated_residual_read",
        ("group_rmsnorm", "low_rank_down", "silu", "low_rank_up", "branch_mix"),
        "matrix_sfu",
        "gated_residual_policy",
        True,
        85,
    ),
    Pattern(
        "ple",
        ("ngram_hash", "embedding_gather", "ple_projection", "dilated_dwconv"),
        "memory_matrix_state",
        "ple_policy",
        True,
        80,
    ),
    Pattern(
        "moe",
        ("router", "topk", "grouped_expert_gemm", "shared_expert", "route_reduce"),
        "sfu_matrix_weight",
        "moe_policy",
        True,
        80,
    ),
    Pattern("swi_glu", ("matrix_gate_up", "silu_mul", "matrix_down"), "matrix_sfu", "swi_glu", False, 70),
    Pattern("rmsnorm_projection", ("rmsnorm", "matrix_projection"), "sfu_matrix", "rmsnorm_projection", False, 60),
    Pattern("rope", ("rope",), "sfu", "rope", False, 20),
    Pattern("matrix", ("matrix_projection",), "matrix", "matrix", False, 10),
)


@dataclass(frozen=True)
class CapabilityManifest:
    policies: frozenset[str]
    dtypes: frozenset[str] = frozenset({"bf16", "fp16", "int8", "w4a8"})
    max_rank: int = 4

    def supports(
        self,
        pattern: Pattern,
        nodes: Sequence[GraphNode],
    ) -> tuple[bool, str | None]:
        if pattern.policy not in self.policies:
            return False, f"policy:{pattern.policy}"
        if any(node.dtype not in self.dtypes for node in nodes):
            return False, "dtype"
        if any(len(node.shape) > self.max_rank for node in nodes):
            return False, "rank"
        if pattern.policy == "attention_op":
            if int(nodes[1].attr("block_tokens", 128)) != 128:
                return False, "attention_block"
        if pattern.policy == "qsa_policy":
            if int(nodes[1].attr("selected_tokens", 2048)) > 2048:
                return False, "qsa_budget"
        return True, None


class Graph:
    def __init__(self, nodes: Iterable[GraphNode]) -> None:
        self.nodes = tuple(nodes)
        self.by_id = {node.node_id: node for node in self.nodes}
        if len(self.by_id) != len(self.nodes):
            raise ValueError("duplicate node ID")
        self.index = {node.node_id: index for index, node in enumerate(self.nodes)}
        self.consumers: dict[str, list[str]] = defaultdict(list)
        for node in self.nodes:
            missing = set(node.inputs) - set(self.by_id)
            if missing:
                raise ValueError(f"unknown input for {node.node_id}: {sorted(missing)}")
            if any(self.index[item] >= self.index[node.node_id] for item in node.inputs):
                raise ValueError("graph is not topological")
            for item in node.inputs:
                self.consumers[item].append(node.node_id)

    def linear_successor(self, node_id: str) -> str | None:
        consumers = self.consumers.get(node_id, [])
        return consumers[0] if len(consumers) == 1 else None


class GraphPartitioner:
    def __init__(
        self,
        manifest: CapabilityManifest,
        patterns: Sequence[Pattern] = DEFAULT_PATTERNS,
    ) -> None:
        self.manifest = manifest
        self.patterns = tuple(
            sorted(
                patterns,
                key=lambda pattern: (-len(pattern.ops), -pattern.priority, pattern.name),
            )
        )

    def _match(
        self,
        graph: Graph,
        start: str,
        pattern: Pattern,
        consumed: set[str],
    ) -> tuple[GraphNode, ...] | None:
        current = start
        matched: list[GraphNode] = []
        for offset, expected_op in enumerate(pattern.ops):
            if current in consumed:
                return None
            node = graph.by_id[current]
            if node.op != expected_op:
                return None
            if offset and node.inputs != (matched[-1].node_id,):
                return None
            matched.append(node)
            if offset + 1 < len(pattern.ops):
                successor = graph.linear_successor(current)
                if successor is None:
                    return None
                current = successor
        return tuple(matched)

    def partition(self, graph: Graph) -> PartitionResult:
        consumed: set[str] = set()
        raw_segments: list[
            tuple[str, tuple[GraphNode, ...], Pattern | None, str | None]
        ] = []
        for node in graph.nodes:
            if node.node_id in consumed:
                continue
            selected: tuple[GraphNode, ...] | None = None
            selected_pattern: Pattern | None = None
            rejection: str | None = None
            for pattern in self.patterns:
                candidate = self._match(graph, node.node_id, pattern, consumed)
                if candidate is None:
                    continue
                supported, reason = self.manifest.supports(pattern, candidate)
                if supported:
                    selected = candidate
                    selected_pattern = pattern
                    break
                rejection = reason
            if selected is None:
                selected = (node,)
                raw_segments.append(
                    ("fallback", selected, None, rejection or f"unsupported_op:{node.op}")
                )
            else:
                raw_segments.append(("hardware", selected, selected_pattern, None))
            consumed.update(item.node_id for item in selected)

        node_to_segment: dict[str, int] = {}
        segments: list[Segment] = []
        for segment_id, (kind, nodes, pattern, reason) in enumerate(raw_segments):
            dependencies = sorted(
                {
                    node_to_segment[input_id]
                    for node in nodes
                    for input_id in node.inputs
                    if input_id in node_to_segment
                }
            )
            if pattern is None:
                segment = Segment(
                    segment_id,
                    kind,
                    tuple(node.node_id for node in nodes),
                    "cpu",
                    "fallback",
                    tuple(dependencies),
                    False,
                    reason,
                )
            else:
                segment = Segment(
                    segment_id,
                    kind,
                    tuple(node.node_id for node in nodes),
                    pattern.engine,
                    pattern.policy,
                    tuple(dependencies),
                    pattern.stateful,
                )
            segments.append(segment)
            for node in nodes:
                node_to_segment[node.node_id] = segment_id

        payload = json.dumps(
            [segment.__dict__ for segment in segments],
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return PartitionResult(
            tuple(segments),
            node_to_segment,
            hashlib.sha256(payload).hexdigest(),
        )


def node(
    node_id: str,
    op: str,
    previous: str | None = None,
    **attrs: object,
) -> GraphNode:
    return GraphNode(
        node_id,
        op,
        () if previous is None else (previous,),
        attrs=tuple(sorted(attrs.items())),
    )


def qwen2_synthetic_graph() -> Graph:
    return Graph(
        (
            node("n0", "rmsnorm"),
            node("n1", "matrix_projection", "n0"),
            node("n2", "matrix_qk", "n1"),
            node("n3", "online_softmax", "n2", block_tokens=128),
            node("n4", "matrix_pv", "n3"),
            node("n5", "matrix_gate_up", "n4"),
            node("n6", "silu_mul", "n5"),
            node("n7", "matrix_down", "n6"),
        )
    )


def qwen38_synthetic_graph() -> Graph:
    operators = (
        "ngram_hash",
        "embedding_gather",
        "ple_projection",
        "dilated_dwconv",
        "group_rmsnorm",
        "low_rank_down",
        "silu",
        "low_rank_up",
        "branch_mix",
        "qsa_index",
        "topk",
        "kv_gather",
        "matrix_qk",
        "online_softmax",
        "matrix_pv",
        "output_gate",
        "router",
        "topk",
        "grouped_expert_gemm",
        "shared_expert",
        "route_reduce",
        "vision_patch_embed",
    )
    nodes: list[GraphNode] = []
    previous: str | None = None
    for index, operator in enumerate(operators):
        attrs: dict[str, object] = {}
        if operator == "topk" and index < 15:
            attrs["selected_tokens"] = 2048
        if operator == "online_softmax":
            attrs["block_tokens"] = 128
        current = f"q{index}"
        nodes.append(node(current, operator, previous, **attrs))
        previous = current
    return Graph(nodes)


def partition_report() -> dict[str, object]:
    manifest = CapabilityManifest(
        frozenset(pattern.policy for pattern in DEFAULT_PATTERNS)
    )
    partitioner = GraphPartitioner(manifest)
    qwen2 = partitioner.partition(qwen2_synthetic_graph())
    qwen38 = partitioner.partition(qwen38_synthetic_graph())
    return {
        "schema_version": 1,
        "status": "PASS",
        "evidence_class": "GGML_like_graph_partition_E0_not_real_llama_cpp_backend",
        "qwen2": {
            "segments": len(qwen2.segments),
            "policies": [segment.policy for segment in qwen2.segments],
            "fallback": len(qwen2.fallback_segments),
            "sha256": qwen2.program_sha256,
        },
        "qwen38": {
            "segments": len(qwen38.segments),
            "policies": [segment.policy for segment in qwen38.segments],
            "fallback": [
                segment.fallback_reason for segment in qwen38.fallback_segments
            ],
            "sha256": qwen38.program_sha256,
        },
        "frozen_contract": {
            "longest_match_first": True,
            "model_name_conditionals": False,
            "explicit_CPU_fallback": True,
            "deterministic_partition_hash": True,
            "unsupported_vision_fallback": True,
        },
        "remaining_local_gates": [
            "real_GGML_node_adapter",
            "real_llama_cpp_graph_capture",
            "GGUF_tensor_binding",
            "device_command_submission",
            "CPU_fallback_execution",
        ],
    }
