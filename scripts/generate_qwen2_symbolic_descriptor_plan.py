#!/usr/bin/env python3
"""Generate address-complete descriptor chains while public dtype codes are open."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work/upstream/llama_cpp/gguf-py"))
sys.path.insert(0, str(ROOT / "src"))
from gguf import GGUFReader
from heteronpu.precision_policy import fp32_boundary_indices, node_dtype

NULL_INDEX = 0xFFFFFF
DDR_WEIGHT_BASE = 0x1_0000_0000
DDR_ACTIVATION_BASE = 0x2_0000_0000
DDR_CONTROL_BASE = 0x4_0000_0000
DDR_KV_BASE = 0x5_0000_0000


def align(value: int, boundary: int = 64) -> int:
    return (value + boundary - 1) // boundary * boundary


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def product(shape: list[int] | tuple[int, ...]) -> int:
    return math.prod(int(value) for value in shape)


def binding_key(binding: dict) -> str:
    kind = binding["kind"]
    if kind == "gguf_tensor":
        return f"gguf:{binding['name']}"
    if kind == "ggml_node":
        return f"ggml:{binding['index']}"
    if kind == "runtime_position":
        return "runtime:position_q1024"
    if kind == "flash_intermediate":
        return f"flash:{binding['layer']}:{binding['name']}"
    if kind == "kv_context":
        return f"kv_context:{binding['layer']}"
    raise ValueError(f"unknown binding kind {kind}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--gguf", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--encoding", type=Path)
    parser.add_argument("--precision-policy", type=Path, help="Approved evidence-backed FP32 boundary policy; omit only to reproduce legacy BF16")
    args = parser.parse_args()
    args.out = args.out.resolve()
    args.report = args.report.resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    encoding_approved = bool(args.encoding and
                             json.loads(args.encoding.read_text())["approval_status"] == "APPROVED")

    commands = [json.loads(line) for line in args.manifest.read_text().splitlines()]
    fp32_indices = frozenset()
    if args.precision_policy:
        precision = json.loads(args.precision_policy.read_text())
        assert precision['status'].startswith('APPROVED_')
        assert precision['approved_policy']['matrix_operands_max'] == 'BF16'
        assert precision['approved_policy']['matrix_accumulator'] == 'FP32'
        assert precision['approved_policy']['absolute_error_threshold'] == 0.002
        assert args.out != ROOT/'work/generated/qwen2_q1024_symbolic_descriptors', 'Preserve frozen legacy descriptor artifacts'
        fp32_indices = fp32_boundary_indices(commands)
    reader = GGUFReader(args.gguf, "r")
    gguf = {tensor.name: tensor for tensor in reader.tensors}

    memory: dict[str, dict] = {}
    cursors = {
        "DDR_READONLY": DDR_WEIGHT_BASE,
        "DDR_WORKSPACE": DDR_ACTIVATION_BASE,
        "DDR_CONTROL": DDR_CONTROL_BASE,
        "DDR_KV": DDR_KV_BASE,
    }

    def allocate(key: str, binding: dict) -> dict:
        if key in memory:
            return memory[key]
        kind = binding["kind"]
        if kind == "gguf_tensor":
            tensor = gguf[binding["name"]]
            shape = [int(value) for value in tensor.shape]
            if int(tensor.tensor_type) == 30:
                dtype, byte_length = "BF16", int(tensor.n_bytes)
            elif int(tensor.tensor_type) == 0:
                dtype, byte_length = "FP32", int(tensor.n_bytes)
            else:
                raise ValueError(f"unsupported exact GGUF storage type {tensor.tensor_type}: {binding['name']}")
            region = "DDR_READONLY"
        elif kind == "ggml_node":
            ggml_shape = [int(value) for value in binding["shape"]]
            highest_nonunit = max((index for index, value in enumerate(ggml_shape) if value != 1),
                                  default=0)
            rank = max(2, highest_nonunit + 1)
            shape = list(reversed(ggml_shape[:rank]))
            dtype = node_dtype(binding, fp32_indices)
            byte_length, region = product(shape) * (4 if dtype == 'FP32' else 2), 'DDR_WORKSPACE'
        elif kind == "runtime_position":
            shape, dtype, byte_length, region = [1024], "INT32", 4096, "DDR_CONTROL"
        elif kind == "flash_intermediate":
            # A tile is materialized; a sequence-square score tensor is forbidden.
            shape, region = [16, 32], "DDR_WORKSPACE"
            if binding["name"] == "qk_score_tile":
                dtype, byte_length = "FP32", 2048
            elif binding["name"] == "probability_tile":
                dtype, byte_length = "BF16", 1024
            else:
                raise ValueError(f"unknown FlashAttention intermediate {binding['name']}")
        else:
            raise ValueError(f"binding {key} has no ordinary tensor allocation")
        address = align(cursors[region])
        cursors[region] = address + align(byte_length)
        memory[key] = {
            "key": key, "kind": kind, "name": binding.get("name", key),
            "address": address, "byte_length": byte_length, "shape": shape,
            "dtype_symbol": dtype, "dtype_code": None, "region": region,
            "alignment": 64,
        }
        return memory[key]

    # Allocate all ordinary tensors once, independent of per-command descriptor roots.
    for command in commands:
        for binding in command["root_bindings"].values():
            if binding["kind"] != "kv_context":
                allocate(binding_key(binding), binding)

    # Sparse q1024 two-level page-table and KV data regions live in DDR.
    kv_tables = {}
    for layer in range(28):
        table_key = f"kv_page_table:{layer}"
        table_address = align(cursors["DDR_KV"])
        table_bytes = 2 * 1024 * 16  # one 1024-entry root plus one active 1024-entry leaf
        cursors["DDR_KV"] = table_address + table_bytes
        data_key = f"kv_data:{layer}"
        data_address = align(cursors["DDR_KV"])
        data_bytes = 1024 * 2 * 128 * 2 * 2  # tokens * KV heads * dim * BF16 * K/V
        cursors["DDR_KV"] = data_address + data_bytes
        kv_tables[layer] = {
            "table_key": table_key, "table_address": table_address,
            "table_bytes": table_bytes, "data_key": data_key,
            "data_address": data_address, "data_bytes": data_bytes,
            "page_tokens": 16, "logical_pages": 64, "pte_bytes": 16,
        }

    command_roots = {int(root) for command in commands for root in command["roots"].values()}
    tail = max(command_roots) + 1
    chains: dict[int, dict] = {}
    table_roots = {layer: tail + layer for layer in range(28)}
    tail += len(table_roots)
    matrix_shape_errors = 0

    def append_chain(root: int, records: list[dict], binding: dict, operation: str, role: str) -> None:
        nonlocal tail
        indices = [root]
        for _ in records[1:]:
            indices.append(tail)
            tail += 1
        materialized = []
        for offset, record in enumerate(records):
            materialized.append({
                "index": indices[offset], "record_type": record["record_type"],
                "next_index": indices[offset + 1] if offset + 1 < len(indices) else NULL_INDEX,
                **{key: value for key, value in record.items() if key != "record_type"},
            })
        if root in chains:
            raise ValueError(f"duplicate descriptor root {root}")
        chains[root] = {"root": root, "operation": operation, "role": role,
                        "binding": binding, "records": materialized}

    def ordinary_records(entry: dict) -> list[dict]:
        shape = entry["shape"]
        padded = (shape + [1, 1, 1, 1])[:4]
        strides = [product(padded[index + 1:]) for index in range(3)]
        return [
            {"record_type": "tensor_base", "address": entry["address"],
             "dtype_symbol": entry["dtype_symbol"], "dtype_code": None,
             "layout": "contiguous", "rank": min(len(shape), 4)},
            {"record_type": "shape4", "dims": padded},
            {"record_type": "stride3", "strides_elements": strides},
        ]

    for command in commands:
        operation, opcode = command["operation"], command["opcode"]
        for role, root in command["roots"].items():
            binding = command["root_bindings"][str(root)]
            if binding["kind"] == "kv_context":
                layer = int(binding["layer"])
                table_root = table_roots[layer]
                records = [
                    {"record_type": "kv_context32", "sequence_id": 0, "layer_id": layer,
                     "kv_head_id": 0},
                    {"record_type": "kv_range32", "token_start": 0, "token_count": 1024},
                    {"record_type": "kv_table", "page_table_tensor_index": table_root,
                     "physical_page_limit": 4096, "page_id_bits": 32,
                     "levels": 2, "page_tokens": 16, "pte_bytes": 16},
                    {"record_type": "kv_epoch32", "generation": 0,
                     "logical_page_count": 64},
                ]
            else:
                entry = memory[binding_key(binding)]
                records = ordinary_records(entry)
                if role == "src0" and command["engine"] == "matrix":
                    if opcode == "matrix_qk":
                        m, n, k = 16, 32, 128
                    elif opcode == "matrix_pv":
                        m, n, k = 16, 128, 32
                    else:
                        src_shape = entry["shape"]
                        dst_binding = command["root_bindings"][str(command["roots"]["dst"])]
                        dst_shape = memory[binding_key(dst_binding)]["shape"]
                        m, n, k = int(src_shape[0]), int(dst_shape[-1]), int(src_shape[-1])
                        weight_binding = command["root_bindings"][str(command["roots"]["src1"])]
                        weight_shape = memory[binding_key(weight_binding)]["shape"]
                        if weight_shape[:2] != [k, n]:
                            matrix_shape_errors += 1
                    records += [
                        {"record_type": "matrix_op", "m": m, "n": n, "k": k,
                         "dataflow": "OS", "quant_mode": "none"},
                        {"record_type": "matrix_aux", "bias_index": NULL_INDEX,
                         "activation": "none", "no_pool": True, "subarray_mask": 1},
                    ]
                    if opcode in {"matrix_qk", "matrix_pv"}:
                        records.append({"record_type": "attention_op", "backend": "hierarchical_block128",
                                        "block_tokens": 128, "q_heads": 12, "kv_heads": 2,
                                        "head_dim": 128, "rotary_dim": 128,
                                        "query_tile": 16, "key_tile": 32})
                elif role == "src0" and command["engine"] == "sfu":
                    records.append({"record_type": "sfu_program_symbolic", "opcode": opcode})
            append_chain(int(root), records, binding, operation, role)

    # Page-table tensor roots are referenced by kv_table records but not command roots.
    for layer, root in table_roots.items():
        info = kv_tables[layer]
        binding = {"kind": "kv_page_table", "layer": layer}
        records = [
            {"record_type": "tensor_base", "address": info["table_address"],
             "dtype_symbol": "INT32", "dtype_code": None,
             "layout": "contiguous", "rank": 3},
            {"record_type": "shape4", "dims": [2, 1024, 4, 1]},
            {"record_type": "stride3", "strides_elements": [4096, 4, 1]},
        ]
        append_chain(root, records, binding, f"kv_table_l{layer}", "metadata")

    root_coverage = command_roots <= set(chains)
    all_indices = []
    for chain in chains.values():
        all_indices.extend(record["index"] for record in chain["records"])
    unique_indices = len(all_indices) == len(set(all_indices))
    max_chain = max(len(chain["records"]) for chain in chains.values())
    dtype_symbols = sorted({entry["dtype_symbol"] for entry in memory.values()} | {"INT32"})
    record_type_counts: dict[str, int] = {}
    for chain in chains.values():
        for record in chain["records"]:
            record_type = record["record_type"]
            record_type_counts[record_type] = record_type_counts.get(record_type, 0) + 1

    intervals = sorted((entry["address"], entry["address"] + align(entry["byte_length"]), key)
                       for key, entry in memory.items())
    intervals += sorted((item["table_address"], item["table_address"] + item["table_bytes"],
                         item["table_key"]) for item in kv_tables.values())
    intervals += sorted((item["data_address"], item["data_address"] + item["data_bytes"],
                         item["data_key"]) for item in kv_tables.values())
    intervals.sort()
    overlaps = sum(1 for left, right in zip(intervals, intervals[1:]) if left[1] > right[0])
    full_score_matrix = any(entry["kind"] == "flash_intermediate" and
                            ((entry["name"] == "qk_score_tile" and entry["byte_length"] > 2048) or
                             (entry["name"] == "probability_tile" and entry["byte_length"] > 1024))
                            for entry in memory.values())
    first_embd = next(entry for entry in memory.values() if entry["kind"] == "ggml_node" and
                      entry["name"] == "embd")
    first_q_rope = next(entry for entry in memory.values() if entry["kind"] == "ggml_node" and
                        entry["name"] == "Qcur-0" and entry["shape"] == [1024, 12, 128])
    checks = {
        "commands_588": len(commands) == 588,
        "all_command_roots_covered": root_coverage,
        "descriptor_indices_unique": unique_indices,
        "chain_length_lte_16": max_chain <= 16,
        "descriptor_index_24bit": max(all_indices) < NULL_INDEX,
        "descriptor_fits_shared_l2": (max(all_indices) + 1) * 16 <= 1536 * 1024,
        "addresses_64bit": all(end <= (1 << 64) for _, end, _ in intervals),
        "addresses_64byte_aligned": all(start % 64 == 0 for start, _, _ in intervals),
        "address_overlap_zero": overlaps == 0,
        "no_full_score_matrix": not full_score_matrix,
        "kv_layers_28": len(kv_tables) == 28,
        "matrix_program_records_252": record_type_counts.get("matrix_op") == 252 and
                                      record_type_counts.get("matrix_aux") == 252,
        "sfu_program_records_308": record_type_counts.get("sfu_program_symbolic") == 308,
        "attention_policy_records_56": record_type_counts.get("attention_op") == 56,
        "matrix_gemm_shapes_consistent": matrix_shape_errors == 0,
        "device_row_major_shapes": first_embd["shape"] == [1024, 1536] and
                                   first_q_rope["shape"] == [1024, 12, 128],
        ("ggml_device_precision_policy" if args.precision_policy else "ggml_device_boundaries_bf16"): all(entry['dtype_symbol'] == ('FP32' if int(entry['key'].split(':')[1]) in fp32_indices else 'BF16')
                                            for entry in memory.values() if entry['kind'] == 'ggml_node'),
        "kv_record_sets_28": all(record_type_counts.get(name) == 28 for name in
                                  ("kv_context32", "kv_range32", "kv_table", "kv_epoch32")),
        "dtype_codes_unassigned": all(entry["dtype_code"] is None for entry in memory.values()),
    }
    if not all(checks.values()):
        raise SystemExit(f"symbolic descriptor plan failed: {checks}")

    memory_path = args.out / "tensor_memory_map.json"
    chain_path = args.out / "descriptor_chains.jsonl"
    memory_payload = {
        "schema_version": 1, "status": "SYMBOLIC_DTYPE_NOT_EXECUTABLE",
        "regions": {name: {"base": base, "end": cursors[name],
                            "bytes": cursors[name] - base}
                    for name, base in (("DDR_READONLY", DDR_WEIGHT_BASE),
                                       ("DDR_WORKSPACE", DDR_ACTIVATION_BASE),
                                       ("DDR_CONTROL", DDR_CONTROL_BASE),
                                       ("DDR_KV", DDR_KV_BASE))},
        "tensors": sorted(memory.values(), key=lambda item: item["address"]),
        "kv": [kv_tables[layer] for layer in range(28)],
    }
    memory_path.write_text(json.dumps(memory_payload, indent=2, sort_keys=True) + "\n")
    chain_path.write_text("".join(json.dumps(chains[root], sort_keys=True, separators=(",", ":")) + "\n"
                                  for root in sorted(chains)))
    report = {
        "schema_version": 1,
        "status": "PASS_SYMBOLIC_DESCRIPTOR_TOPOLOGY",
        "evidence_class": "address_and_chain_complete_but_not_packed_or_executable",
        "public_encoding_approved": encoding_approved,
        "precision_policy": "bf16_matrix_fp32_evidence_boundaries" if args.precision_policy else "legacy_all_bf16",
        "precision_policy_sha256": sha(args.precision_policy) if args.precision_policy else None,
        "fp32_boundary_node_count": len(fp32_indices),
        "commands": len(commands), "command_roots": len(command_roots),
        "descriptor_chains": len(chains), "descriptor_records": len(all_indices),
        "descriptor_storage_bytes": (max(all_indices) + 1) * 16,
        "max_chain_records": max_chain, "memory_objects": len(intervals),
        "record_type_counts": dict(sorted(record_type_counts.items())),
        "dtype_symbols": dtype_symbols, "dtype_codes_assigned": False,
        "kv_layers": len(kv_tables), "kv_page_tokens": 16,
        "flash_score_tile_bytes": 2048, "flash_probability_tile_bytes": 1024,
        "address_overlaps": overlaps,
        "checks": checks,
        "generated": {
            "memory_map": str(memory_path), "memory_map_sha256": sha(memory_path),
            "descriptor_chains": str(chain_path), "descriptor_chains_sha256": sha(chain_path),
        },
        "blocker": None if encoding_approved else
                   "approve public tensor_base dtype codes and SFU_PROGRAM before packing",
        "non_claims": [
            "symbolic records are not a packed descriptor image",
            "address planning does not execute payload RTL",
            "conservative DDR workspace allocation is not an on-chip SRAM allocation",
        ],
    }
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "chains": len(chains),
                      "records": len(all_indices), "objects": len(intervals),
                      "overlaps": overlaps}, sort_keys=True))


if __name__ == "__main__":
    main()
