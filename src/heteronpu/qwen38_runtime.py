"""Executable text-only E0 reference for Qwen3.8-Flash-Next.

The tiny model preserves the official text operator boundaries and persistent
state semantics. It is not an official-weight model or a performance claim.
"""
from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Sequence

from .moe_router import ExpertWeights, MoeExecution, execute_moe
from .qwen38_math import (
    Matrix, TinyQwen38Config, TraceEvent, Vector, _matrix, _vector, add, rmsnorm,
)
from .qwen38_gdn_layer import GDNState, GDNWeights
from .qwen38_ple import GatedResidualWeights, PLEState, PLEWeights
from .qwen38_qsa_layer import QSAState, QSAWeights

@dataclass
class LayerWeights:
    layer_type: str
    attention_gr: GatedResidualWeights
    mlp_gr: GatedResidualWeights
    gdn: GDNWeights | None
    qsa: QSAWeights | None
    ple: PLEWeights | None
    moe_router: Matrix
    experts: tuple[ExpertWeights, ...]
    shared_expert: ExpertWeights
    shared_gate: Vector


@dataclass
class LayerState:
    gdn: GDNState | None = None
    qsa: QSAState | None = None
    ple: PLEState | None = None

    def copy(self) -> "LayerState":
        return LayerState(
            self.gdn.copy() if self.gdn is not None else None,
            self.qsa.copy() if self.qsa is not None else None,
            self.ple.copy() if self.ple is not None else None,
        )


@dataclass
class ModelState:
    token_index: int
    layers: list[LayerState]

    def copy(self) -> "ModelState":
        return ModelState(self.token_index, [layer.copy() for layer in self.layers])


@dataclass(frozen=True)
class TokenResult:
    hidden: Vector
    hyper: Vector
    trace: tuple[TraceEvent, ...]
    qsa_selected: tuple[tuple[int, ...], ...]
    routes: tuple[tuple[int, ...], ...]


@dataclass
class TinyQwen38TextModel:
    config: TinyQwen38Config
    embeddings: Matrix
    layers: tuple[LayerWeights, ...]
    final_gr: GatedResidualWeights

    @classmethod
    def random(cls, config: TinyQwen38Config | None = None, seed: int = 38) -> "TinyQwen38TextModel":
        config = config or TinyQwen38Config()
        rng = random.Random(seed)
        embeddings = _matrix(rng, config.vocab_size, config.hidden_size, 0.30)
        layers: list[LayerWeights] = []
        for layer_index, layer_type in enumerate(config.layer_pattern):
            gdn = GDNWeights.random(rng, config) if layer_type == "linear_attention" else None
            qsa = QSAWeights.random(rng, config) if layer_type == "qwen_sparse_attention" else None
            ple = PLEWeights.random(rng, config, layer_index) if layer_index in config.ple_layer_ids else None
            experts = tuple(ExpertWeights.random(rng, config.hidden_size, config.expert_intermediate) for _ in range(config.num_experts))
            layers.append(
                LayerWeights(
                    layer_type,
                    GatedResidualWeights.random(rng, config.branches, config.hidden_size, config.hc_lowrank),
                    GatedResidualWeights.random(rng, config.branches, config.hidden_size, config.hc_lowrank),
                    gdn,
                    qsa,
                    ple,
                    _matrix(rng, config.num_experts, config.hidden_size),
                    experts,
                    ExpertWeights.random(rng, config.hidden_size, config.shared_intermediate),
                    _vector(rng, config.hidden_size),
                )
            )
        final_gr = GatedResidualWeights.random(rng, config.branches, config.hidden_size, config.hc_lowrank)
        return cls(config, embeddings, tuple(layers), final_gr)

    def initial_state(self) -> ModelState:
        states: list[LayerState] = []
        for layer in self.layers:
            states.append(
                LayerState(
                    layer.gdn.initial_state() if layer.gdn else None,
                    QSAState() if layer.qsa else None,
                    layer.ple.initial_state() if layer.ple else None,
                )
            )
        return ModelState(0, states)

    def step(self, token_id: int, state: ModelState) -> tuple[TokenResult, ModelState]:
        cfg = self.config
        if not 0 <= int(token_id) < cfg.vocab_size:
            raise ValueError("token id")
        state = state.copy()
        position = state.token_index
        hidden0 = self.embeddings[int(token_id)]
        hyper: Vector = tuple(x for _ in range(cfg.branches) for x in hidden0)
        trace: list[TraceEvent] = [TraceEvent.make(position, -1, "TOKEN_EMBED", "memory", token_id=int(token_id))]
        selected_records: list[tuple[int, ...]] = []
        route_records: list[tuple[int, ...]] = []

        for layer_index, (layer, layer_state) in enumerate(zip(self.layers, state.layers, strict=True)):
            if layer.ple is not None:
                assert layer_state.ple is not None
                ple_output, layer_state.ple, indices = layer.ple.step(hyper, int(token_id), layer_state.ple)
                hyper = add(hyper, ple_output)
                trace.extend(
                    (
                        TraceEvent.make(position, layer_index, "PLE_NGRAM_HASH_LOOKUP", "state", rows=len(indices)),
                        TraceEvent.make(position, layer_index, "PLE_KEY_VALUE_PROJECTION", "matrix"),
                        TraceEvent.make(position, layer_index, "PLE_GATE_DILATED_DWCONV", "sfu", channels=len(ple_output)),
                    )
                )

            mixed, inject = layer.attention_gr.read(hyper)
            trace.append(TraceEvent.make(position, layer_index, "GR_ATTN_READ", "matrix", branches=cfg.branches))
            if layer.layer_type == "linear_attention":
                assert layer.gdn is not None and layer_state.gdn is not None
                block, layer_state.gdn = layer.gdn.step(mixed, layer_state.gdn)
                trace.extend(
                    (
                        TraceEvent.make(position, layer_index, "GDN_INPUT_PROJECTIONS", "matrix"),
                        TraceEvent.make(position, layer_index, "GDN_CAUSAL_CONV", "state", kernel=cfg.gdn_conv_kernel),
                        TraceEvent.make(position, layer_index, "GDN_RECURRENT_STATE_UPDATE", "state", bytes=layer_state.gdn.recurrent.geometry.state_bytes),
                        TraceEvent.make(position, layer_index, "GDN_GATED_NORM_OUT_PROJ", "sfu"),
                    )
                )
            else:
                assert layer.qsa is not None and layer_state.qsa is not None
                qsa_result, layer_state.qsa = layer.qsa.step(mixed, position, layer_state.qsa)
                block = qsa_result.output
                selected_records.append(qsa_result.selected_tokens)
                trace.extend(
                    (
                        TraceEvent.make(position, layer_index, "QSA_INDEX_PROJECTION", "matrix"),
                        TraceEvent.make(position, layer_index, "QSA_COMPRESS_TOPK", "sfu", selected=len(qsa_result.selected_tokens)),
                        TraceEvent.make(position, layer_index, "SPARSE_QKV_PROJECTION", "matrix"),
                        TraceEvent.make(position, layer_index, "SPARSE_QK_ONLINE_SOFTMAX_PV", "matrix_sfu", selected=len(qsa_result.selected_tokens)),
                        TraceEvent.make(position, layer_index, "ATTENTION_OUTPUT_GATE_PROJECTION", "matrix_sfu"),
                    )
                )
            hyper = layer.attention_gr.write(hyper, block, inject)
            trace.append(TraceEvent.make(position, layer_index, "GR_ATTN_WRITE", "sfu"))

            mixed, inject = layer.mlp_gr.read(hyper)
            trace.append(TraceEvent.make(position, layer_index, "GR_MOE_READ", "matrix", branches=cfg.branches))
            moe: MoeExecution = execute_moe(
                mixed,
                router=layer.moe_router,
                experts=layer.experts,
                top_k=cfg.top_k,
                shared_expert=layer.shared_expert,
                shared_gate=layer.shared_gate,
            )
            route_records.append(tuple(route.expert_id for route in moe.routes))
            trace.extend(
                (
                    TraceEvent.make(position, layer_index, "MOE_ROUTER_TOPK", "sfu", top_k=cfg.top_k),
                    TraceEvent.make(position, layer_index, "MOE_ROUTED_EXPERT_GEMM", "matrix", active=len(moe.routes)),
                    TraceEvent.make(position, layer_index, "MOE_SHARED_EXPERT", "matrix_sfu"),
                )
            )
            hyper = layer.mlp_gr.write(hyper, moe.output, inject)
            trace.append(TraceEvent.make(position, layer_index, "GR_MOE_WRITE", "sfu"))

        hidden, _ = self.final_gr.read(hyper)
        hidden = rmsnorm(hidden)
        trace.append(TraceEvent.make(position, len(self.layers), "FINAL_HYPER_MERGE_RMSNORM", "sfu"))
        state.token_index += 1
        return TokenResult(hidden, hyper, tuple(trace), tuple(selected_records), tuple(route_records)), state

    def run(self, tokens: Sequence[int], state: ModelState | None = None) -> tuple[tuple[TokenResult, ...], ModelState]:
        state = state.copy() if state is not None else self.initial_state()
        results: list[TokenResult] = []
        for token in tokens:
            result, state = self.step(int(token), state)
            results.append(result)
        return tuple(results), state


def trace_operator_set(results: Sequence[TokenResult]) -> frozenset[str]:
    return frozenset(event.op for result in results for event in result.trace)
