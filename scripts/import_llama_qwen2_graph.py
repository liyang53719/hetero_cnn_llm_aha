#!/usr/bin/env python3
"""Lower the pinned q1024 llama.cpp Qwen2 graph to traceable Command128 ops."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "work/upstream/llama_cpp/gguf-py"))

from gguf import GGUFReader
from heteronpu.segment_compiler import compile_segment


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--gguf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output = args.output.resolve()

    rows = []
    for line in args.graph.read_text().splitlines():
        fields = line.split("\t")
        rows.append({
            "index": int(fields[0]), "name": fields[1], "op": fields[2],
            "dtype": fields[3], "shape": [int(value) for value in fields[4].split(",")],
            "sources": [] if len(fields) < 6 or not fields[5] else fields[5].split(","),
        })
    by_name_op = defaultdict(list)
    for row in rows:
        by_name_op[(row["name"], row["op"])].append(row)

    def node(name: str, op: str) -> dict:
        matches = by_name_op[(name, op)]
        if len(matches) != 1:
            raise ValueError(f"expected one GGML node {name}/{op}, got {len(matches)}")
        return matches[0]

    def tensor_binding(name: str) -> dict:
        return {"kind": "gguf_tensor", "name": name}

    def node_binding(row: dict) -> dict:
        return {"kind": "ggml_node", "index": row["index"], "name": row["name"],
                "op": row["op"], "dtype": row["dtype"], "shape": row["shape"]}

    reader = GGUFReader(args.gguf, "r")
    tensors = {tensor.name: tuple(int(value) for value in tensor.shape)
               for tensor in reader.tensors}
    required = ["token_embd.weight", "output_norm.weight"]
    for layer in range(28):
        required += [
            f"blk.{layer}.attn_norm.weight", f"blk.{layer}.attn_q.weight",
            f"blk.{layer}.attn_q.bias", f"blk.{layer}.attn_k.weight",
            f"blk.{layer}.attn_k.bias", f"blk.{layer}.attn_v.weight",
            f"blk.{layer}.attn_v.bias", f"blk.{layer}.attn_output.weight",
            f"blk.{layer}.ffn_norm.weight", f"blk.{layer}.ffn_gate.weight",
            f"blk.{layer}.ffn_up.weight", f"blk.{layer}.ffn_down.weight",
        ]
    missing = sorted(set(required) - set(tensors))

    operations, bindings = [], []
    descriptor_index = 0x1000

    def add(op_id: str, engine: str, opcode: str, src0: dict, dst: dict,
            *, src1: dict | None = None, dependency: str | None = None,
            graph_nodes: list[dict] | None = None) -> str:
        nonlocal descriptor_index
        roots = {"src0": descriptor_index}
        descriptor_index += 1
        if src1 is not None:
            roots["src1"] = descriptor_index
            descriptor_index += 1
        roots["dst"] = descriptor_index
        descriptor_index += 1
        raw = {"id": op_id, "engine": engine, "opcode": opcode,
               "src0": roots["src0"], "dst": roots["dst"],
               "depends_on": [] if dependency is None else [dependency]}
        if src1 is not None:
            raw["src1"] = roots["src1"]
        operations.append(raw)
        root_bindings = {str(roots["src0"]): src0, str(roots["dst"]): dst}
        if src1 is not None:
            root_bindings[str(roots["src1"])] = src1
        bindings.append({"operation": op_id, "engine": engine, "opcode": opcode,
                         "roots": roots, "root_bindings": root_bindings,
                         "graph_nodes": [item["index"] for item in (graph_nodes or [])]})
        return op_id

    previous = None
    for layer in range(28):
        prefix = f"l{layer}"
        hidden = node("embd", "GET_ROWS") if layer == 0 else node(f"l_out-{layer-1}", "ADD")
        norm = node(f"norm-{layer}", "RMS_NORM")
        attn_norm = node(f"attn_norm-{layer}", "MUL")
        q_mm, q_add, q_rope = (node(f"Qcur-{layer}", op) for op in ("MUL_MAT", "ADD", "ROPE"))
        k_mm, k_add, k_rope = (node(f"Kcur-{layer}", op) for op in ("MUL_MAT", "ADD", "ROPE"))
        v_mm, v_add = (node(f"Vcur-{layer}", op) for op in ("MUL_MAT", "ADD"))
        flash = next(row for row in rows if row["op"] == "FLASH_ATTN_EXT" and
                     any(f"Qcur-{layer}" in source for source in row["sources"]))
        kqv = node(f"kqv_out-{layer}", "RESHAPE")
        oproj = next(row for row in rows if row["op"] == "MUL_MAT" and
                     f"blk.{layer}.attn_output.weight" in row["sources"])
        attn_residual = node(f"ffn_inp-{layer}", "ADD")
        ffn_norm = node(f"ffn_norm-{layer}", "MUL")
        gate = node(f"ffn_gate-{layer}", "MUL_MAT")
        up = node(f"ffn_up-{layer}", "MUL_MAT")
        swiglu = node(f"ffn_swiglu-{layer}", "GLU")
        down = node(f"ffn_out-{layer}", "MUL_MAT")
        layer_out = node(f"l_out-{layer}", "ADD")

        previous = add(f"{prefix}.input_norm", "sfu", "sfu_rmsnorm", node_binding(hidden),
                       node_binding(attn_norm), src1=tensor_binding(f"blk.{layer}.attn_norm.weight"),
                       dependency=previous, graph_nodes=[norm, attn_norm])
        previous = add(f"{prefix}.q", "matrix", "matrix_gemm", node_binding(attn_norm),
                       node_binding(q_mm), src1=tensor_binding(f"blk.{layer}.attn_q.weight"),
                       dependency=previous, graph_nodes=[q_mm])
        previous = add(f"{prefix}.q_bias", "sfu", "sfu_vector", node_binding(q_mm),
                       node_binding(q_add), src1=tensor_binding(f"blk.{layer}.attn_q.bias"),
                       dependency=previous, graph_nodes=[q_add])
        previous = add(f"{prefix}.q_rope", "sfu", "sfu_rope", node_binding(q_add),
                       node_binding(q_rope), src1={"kind": "runtime_position"},
                       dependency=previous, graph_nodes=[q_rope])
        previous = add(f"{prefix}.k", "matrix", "matrix_gemm", node_binding(attn_norm),
                       node_binding(k_mm), src1=tensor_binding(f"blk.{layer}.attn_k.weight"),
                       dependency=previous, graph_nodes=[k_mm])
        previous = add(f"{prefix}.k_bias", "sfu", "sfu_vector", node_binding(k_mm),
                       node_binding(k_add), src1=tensor_binding(f"blk.{layer}.attn_k.bias"),
                       dependency=previous, graph_nodes=[k_add])
        previous = add(f"{prefix}.k_rope", "sfu", "sfu_rope", node_binding(k_add),
                       node_binding(k_rope), src1={"kind": "runtime_position"},
                       dependency=previous, graph_nodes=[k_rope])
        previous = add(f"{prefix}.v", "matrix", "matrix_gemm", node_binding(attn_norm),
                       node_binding(v_mm), src1=tensor_binding(f"blk.{layer}.attn_v.weight"),
                       dependency=previous, graph_nodes=[v_mm])
        previous = add(f"{prefix}.v_bias", "sfu", "sfu_vector", node_binding(v_mm),
                       node_binding(v_add), src1=tensor_binding(f"blk.{layer}.attn_v.bias"),
                       dependency=previous, graph_nodes=[v_add])
        previous = add(f"{prefix}.kv_append", "kv", "kv_append", node_binding(k_rope),
                       {"kind": "kv_context", "layer": layer}, src1=node_binding(v_add),
                       dependency=previous)
        score = {"kind": "flash_intermediate", "layer": layer, "name": "qk_score_tile"}
        probability = {"kind": "flash_intermediate", "layer": layer, "name": "probability_tile"}
        previous = add(f"{prefix}.qk", "matrix", "matrix_qk", node_binding(q_rope), score,
                       src1=node_binding(k_rope), dependency=previous, graph_nodes=[flash])
        previous = add(f"{prefix}.softmax", "sfu", "sfu_softmax", score, probability,
                       dependency=previous, graph_nodes=[flash])
        previous = add(f"{prefix}.pv", "matrix", "matrix_pv", probability, node_binding(kqv),
                       src1=node_binding(v_add), dependency=previous, graph_nodes=[flash, kqv])
        previous = add(f"{prefix}.oproj", "matrix", "matrix_gemm", node_binding(kqv),
                       node_binding(oproj), src1=tensor_binding(f"blk.{layer}.attn_output.weight"),
                       dependency=previous, graph_nodes=[oproj])
        previous = add(f"{prefix}.attn_residual", "sfu", "sfu_vector", node_binding(oproj),
                       node_binding(attn_residual), src1=node_binding(hidden),
                       dependency=previous, graph_nodes=[attn_residual])
        previous = add(f"{prefix}.post_norm", "sfu", "sfu_rmsnorm", node_binding(attn_residual),
                       node_binding(ffn_norm), src1=tensor_binding(f"blk.{layer}.ffn_norm.weight"),
                       dependency=previous, graph_nodes=[norm, ffn_norm])
        previous = add(f"{prefix}.gate", "matrix", "matrix_gemm", node_binding(ffn_norm),
                       node_binding(gate), src1=tensor_binding(f"blk.{layer}.ffn_gate.weight"),
                       dependency=previous, graph_nodes=[gate])
        previous = add(f"{prefix}.up", "matrix", "matrix_gemm", node_binding(ffn_norm),
                       node_binding(up), src1=tensor_binding(f"blk.{layer}.ffn_up.weight"),
                       dependency=previous, graph_nodes=[up])
        previous = add(f"{prefix}.silu_mul", "sfu", "sfu_activation", node_binding(gate),
                       node_binding(swiglu), src1=node_binding(up), dependency=previous,
                       graph_nodes=[swiglu])
        previous = add(f"{prefix}.down", "matrix", "matrix_gemm", node_binding(swiglu),
                       node_binding(down), src1=tensor_binding(f"blk.{layer}.ffn_down.weight"),
                       dependency=previous, graph_nodes=[down])
        previous = add(f"{prefix}.residual", "sfu", "sfu_vector", node_binding(down),
                       node_binding(layer_out), src1=node_binding(attn_residual),
                       dependency=previous, graph_nodes=[layer_out])

    compiled = compile_segment({"name": "qwen2_q1024_real_ggml_graph_v2", "operations": operations})
    compiled_dict = compiled.to_dict()
    words = [item["word_hex"] for item in compiled_dict["commands"]]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    manifest_path = args.output.with_name("llama_cpp_qwen2_graph_lowering_manifest.jsonl")
    manifest_records = []
    for command, binding in zip(compiled_dict["commands"], bindings, strict=True):
        manifest_records.append({"word": command["word_hex"], **binding})
    manifest_path.write_text("".join(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
                                     for record in manifest_records))
    engine_counts = Counter(item["fields"]["engine"] for item in compiled_dict["commands"])
    op_counts = Counter(row["op"] for row in rows)
    layer_ops = defaultdict(set)
    for row in rows:
        for match in re.finditer(r"(?:-|l)(\d+)(?:\b|\s|\()", row["name"]):
            layer = int(match.group(1))
            if layer < 28:
                layer_ops[layer].add(row["op"])
    checks = {
        "q1024_single_ubatch_graph": rows[0]["shape"][1] == 1024,
        "q1024_hidden_through_layer26": all(node(f"l_out-{layer}", "ADD")["shape"][1] == 1024
                                               for layer in range(27)),
        "last_token_only_layer27_output": node("l_out-27", "ADD")["shape"][1] == 1,
        "nodes": len(rows) == 930,
        "op_inventory": op_counts["MUL_MAT"] == 197 and op_counts["FLASH_ATTN_EXT"] == 28,
        "layer_coverage": len(layer_ops) == 28 and all({"MUL_MAT", "RMS_NORM"} <= layer_ops[i] for i in range(28)),
        "gguf_tensors": len(tensors) == 338 and not missing and "output.weight" not in tensors,
        "command_count": len(words) == 588,
        "engine_counts": engine_counts == {"MATRIX": 252, "SFU_CGRA": 308, "KV": 28},
        "binding_count": len(bindings) == len(words),
        "descriptor_range": descriptor_index < 0xFFFFFF,
        "no_qkv_bundle": not any(item["operation"].endswith(".qkv") for item in bindings),
    }
    if not all(checks.values()):
        raise SystemExit(f"graph import failed: {checks}; missing={missing[:8]}")
    result = {
        "schema_version": 2,
        "status": "PASS_REAL_Q1024_GGML_NODE_TENSOR_COMMAND128_LOWERING",
        "evidence_class": "real_single_ubatch_q1024_graph_with_explicit_node_and_GGUF_tensor_bindings_not_device_execution",
        "model": "Qwen/Qwen2-1.5B-Instruct",
        "revision": "ba1cf1846d7df0a0591d6c00649f57e798519da8",
        "llama_cpp_commit": "0b5be7e4a25862bc2777d0c47eae18788a8c963a",
        "graph": {"nodes": len(rows), "op_counts": dict(sorted(op_counts.items())),
                  "layers": len(layer_ops), "sequence": 1024, "ubatch": 1024,
                  "capture_sha256": sha(args.graph)},
        "gguf": {"sha256": sha(args.gguf), "tensors": len(tensors),
                 "required_bound": len(required), "tied_output_to_token_embedding": True,
                 "missing": missing},
        "lowering": {"operations": len(operations), "commands": len(words),
                     "barriers": len(compiled.barriers), "descriptor_next": descriptor_index,
                     "command_sha256": hashlib.sha256("".join(words).encode()).hexdigest(),
                     "manifest": str(manifest_path.relative_to(ROOT)),
                     "manifest_records": len(manifest_records),
                     "manifest_sha256": sha(manifest_path),
                     "engine_counts": dict(sorted(engine_counts.items())),
                     "commands_per_layer": 21},
        "first_layer_schedule": [record["operation"] for record in manifest_records[:21]],
        "checks": checks,
        "supersedes": {"command_count": 252,
                       "reason": "the prior nine-phase template did not bind GGML nodes and collapsed distinct Q/K/V tensors"},
        "open": ["descriptor_record_image", "device_memory_binding", "real_payload_execution"],
        "non_claim": "traceable graph lowering does not execute the project device backend",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"], "nodes": len(rows), "commands": len(words),
                      "engine_counts": dict(engine_counts),
                      "sha256": result["lowering"]["command_sha256"]}, sort_keys=True))


if __name__ == "__main__":
    main()
