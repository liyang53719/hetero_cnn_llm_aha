#!/usr/bin/env python3
"""Pack a symbolic Qwen2 descriptor plan using an explicitly approved encoding."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

NULL_INDEX = 0xFFFFFF
TYPE = {
    "tensor_base": 0x01, "shape4": 0x02, "stride3": 0x03,
    "matrix_op": 0x10, "matrix_aux": 0x12, "attention_op": 0x13,
    "sfu_program_symbolic": 0x20, "kv_context32": 0x32,
    "kv_range32": 0x33, "kv_table": 0x34, "kv_epoch32": 0x35,
}
OPCODE = {
    "sfu_vector": 0x30, "sfu_reduce": 0x31, "sfu_rmsnorm": 0x32,
    "sfu_softmax": 0x33, "sfu_rope": 0x34, "sfu_activation": 0x35,
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def field(value: int, width: int, name: str) -> int:
    if not 0 <= int(value) < (1 << width):
        raise ValueError(f"{name}={value} does not fit {width} bits")
    return int(value)


def signed_field(value: int, width: int, name: str) -> int:
    if not -(1 << (width - 1)) <= int(value) < (1 << (width - 1)):
        raise ValueError(f"{name}={value} does not fit signed {width} bits")
    return int(value) & ((1 << width) - 1)


def record_word(record_type: int, next_index: int, payload: int) -> int:
    return (field(record_type, 8, "record_type") |
            field(next_index, 24, "next_index") << 32 |
            field(payload, 72, "payload") << 56)


def pack_payload(record: dict, encoding: dict, command: dict | None,
                 chains: dict[int, dict]) -> int:
    kind = record["record_type"]
    dtype = encoding["tensor_base"]["dtype_codes"]
    if kind == "tensor_base":
        address = field(record["address"], 56, "address")
        dtype_code = field(dtype[record["dtype_symbol"]], 4, "dtype")
        rank = field(record["rank"], 4, "rank")
        return ((address & ((1 << 48) - 1)) | dtype_code << 52 |
                rank << 60 | (address >> 48) << 64)
    if kind == "shape4":
        return sum(field(value, 18, f"dim{index}") << (18 * index)
                   for index, value in enumerate(record["dims"]))
    if kind == "stride3":
        return sum(signed_field(value, 24, f"stride{index}") << (24 * index)
                   for index, value in enumerate(record["strides_elements"]))
    if kind == "matrix_op":
        return (field(record["m"], 16, "m") | field(record["n"], 16, "n") << 16 |
                field(record["k"], 24, "k") << 32)
    if kind == "matrix_aux":
        return (field(record["bias_index"], 24, "bias_index") | 1 << 29 |
                1 << 42 | field(record["subarray_mask"], 8, "subarray_mask") << 62)
    if kind == "attention_op":
        return (1 | field(record["block_tokens"], 10, "block_tokens") << 8 |
                field(record["q_heads"], 10, "q_heads") << 18 |
                field(record["kv_heads"], 10, "kv_heads") << 28 |
                field(record["head_dim"], 10, "head_dim") << 38 |
                field(record["rotary_dim"], 10, "rotary_dim") << 48 |
                int(math.log2(record["query_tile"])) << 58 |
                int(math.log2(record["key_tile"])) << 62)
    if kind == "sfu_program_symbolic":
        if command is None:
            raise ValueError("SFU program lacks command context")
        src_chain = chains[int(command["roots"]["src0"])]
        dst_chain = chains[int(command["roots"]["dst"])]
        src_base = next(item for item in src_chain["records"] if item["record_type"] == "tensor_base")
        dst_base = next(item for item in dst_chain["records"] if item["record_type"] == "tensor_base")
        input_count = 2 if "src1" in command["roots"] else 1
        return (field(OPCODE[record["opcode"]], 16, "program_id") |
                input_count << 16 | 1 << 24 |
                field(dtype[src_base["dtype_symbol"]], 4, "input_dtype") << 32 |
                field(dtype[dst_base["dtype_symbol"]], 4, "output_dtype") << 36 |
                16 << 40)
    if kind == "kv_context32":
        return (field(record["sequence_id"], 32, "sequence_id") |
                field(record["layer_id"], 12, "layer_id") << 32 |
                field(record["kv_head_id"], 12, "kv_head_id") << 44)
    if kind == "kv_range32":
        return (field(record["token_start"], 32, "token_start") |
                field(record["token_count"], 32, "token_count") << 32)
    if kind == "kv_table":
        return (field(record["page_table_tensor_index"], 24, "page_table_tensor_index") |
                field(record["physical_page_limit"], 24, "physical_page_limit") << 24 |
                field(record["page_id_bits"], 6, "page_id_bits") << 48 |
                field(record["levels"], 3, "levels") << 54 |
                int(math.log2(record["page_tokens"])) << 57 |
                int(math.log2(record["pte_bytes"])) << 62)
    if kind == "kv_epoch32":
        return (field(record["generation"], 32, "generation") |
                field(record["logical_page_count"], 32, "logical_page_count") << 32)
    raise ValueError(f"unsupported record type {kind}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chains", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--encoding", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--allow-unapproved-test", action="store_true")
    args = parser.parse_args()
    encoding = json.loads(args.encoding.read_text())
    approved = encoding["approval_status"] == "APPROVED"
    if not approved and not args.allow_unapproved_test:
        raise SystemExit("descriptor encoding is not APPROVED")
    commands = [json.loads(line) for line in args.manifest.read_text().splitlines()]
    command_by_operation = {command["operation"]: command for command in commands}
    chain_list = [json.loads(line) for line in args.chains.read_text().splitlines()]
    chains = {int(chain["root"]): chain for chain in chain_list}
    packed = []
    type_counts: dict[str, int] = {}
    for chain in chain_list:
        command = command_by_operation.get(chain["operation"])
        for record in chain["records"]:
            payload = pack_payload(record, encoding, command, chains)
            word = record_word(TYPE[record["record_type"]], int(record["next_index"]), payload)
            packed.append({"index": int(record["index"]), "word": f"0x{word:032x}",
                           "record_type": record["record_type"], "root": int(chain["root"])})
            type_counts[record["record_type"]] = type_counts.get(record["record_type"], 0) + 1
    indices = [record["index"] for record in packed]
    roots = {int(root) for command in commands for root in command["roots"].values()}
    checks = {
        "commands_588": len(commands) == 588,
        "chains_1764": len(chains) == 1764,
        "records_6188": len(packed) == 6188,
        "indices_unique": len(indices) == len(set(indices)),
        "command_roots_present": roots <= set(chains),
        "common_subtype_flags_zero": all((int(item["word"], 16) >> 8) & 0xFFFFFF == 0 for item in packed),
        "record_words_128bit": all(int(item["word"], 16) < (1 << 128) for item in packed),
        "matrix_records_252": type_counts.get("matrix_op") == type_counts.get("matrix_aux") == 252,
        "sfu_program_records_308": type_counts.get("sfu_program_symbolic") == 308,
        "attention_records_56": type_counts.get("attention_op") == 56,
        "kv_record_sets_28": all(type_counts.get(name) == 28 for name in
                                  ("kv_context32", "kv_range32", "kv_table", "kv_epoch32")),
    }
    if not all(checks.values()):
        raise SystemExit(f"packed descriptor validation failed: {checks}")
    args.out = args.out.resolve()
    args.report = args.report.resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    records_path = args.out / "packed_records.jsonl"
    records_path.write_text("".join(json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n"
                                    for item in sorted(packed, key=lambda item: item["index"])))
    report = {
        "schema_version": 1,
        "status": "PASS_PACKED_DESCRIPTOR_IMAGE" if approved else
                  "PASS_TEST_ONLY_UNAPPROVED_ENCODING_NOT_EXECUTABLE",
        "encoding_approved": approved, "test_only_override": args.allow_unapproved_test,
        "commands": len(commands), "chains": len(chains), "records": len(packed),
        "record_type_counts": dict(sorted(type_counts.items())), "checks": checks,
        "encoding_sha256": sha(args.encoding),
        "packed_records": str(records_path), "packed_records_sha256": sha(records_path),
        "non_claim": None if approved else
                     "test packing with an unapproved proposal is not a public descriptor image",
    }
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "records": len(packed),
                      "sha256": report["packed_records_sha256"]}, sort_keys=True))


if __name__ == "__main__":
    main()
