#!/usr/bin/env python3
"""Generate/check C03.3 portable synthetic vectors; no RTL or official inputs."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from heteronpu.shape_layout_contract import evaluate

FIXTURE = Path("tests/fixtures/block_contracts/shape_layout_vectors.json")
LEGACY = Path("tests/fixtures/block_contracts/legacy_layout_vectors.tsv")
SCALA_RESOURCE = Path("chisel/continuous_prefill/src/test/resources/c03_3/legacy_layout_vectors.tsv")
SOURCES = ["chisel/continuous_prefill/src/main/scala/heteronpu/continuous/" + name
           for name in ("Qwen2Block.scala", "HostBlockCommands.scala", "TypedTensorReader.scala", "QwenOwnerProtocol.scala")]


def wire(value):
    """All integers below the metadata envelope are decimal strings, even small ones."""
    if type(value) is int:
        return str(value)
    if isinstance(value, dict):
        return {k: wire(v) for k, v in value.items()}
    if isinstance(value, list):
        return [wire(v) for v in value]
    return value


def cases():
    result = []

    def add(name, operation, inputs, scope, **changes):
        inputs = deepcopy(inputs)
        inputs.update(changes)
        result.append({"id": name, "operation": operation, "scope": scope,
                       "inputs": inputs, "expected": evaluate(operation, inputs)})

    shape = dict(hidden=64, ffn=80, q_heads=4, kv_heads=1, head_dim=32,
                 value_dim=32, query_tokens=3, kv_tokens=1025)
    for name, change in (
        ("decoupled_query_kv", {}),
        ("synthetic_2048_4096_2048", {"hidden": 2048, "ffn": 512, "q_heads": 16,
                                     "kv_heads": 2, "head_dim": 256, "value_dim": 256,
                                     "extra_rows": {"gdn_conv": 8192, "gdn_value": 4096}}),
        ("synthetic_2560_6144_2560", {"hidden": 2560, "ffn": 640, "q_heads": 24,
                                     "kv_heads": 2, "head_dim": 256, "value_dim": 256,
                                     "extra_rows": {"gdn_conv": 10240, "gdn_value": 6144}}),
        ("distinct_value_width", {"value_dim": 64}),
        ("explicit_extra_max_row", {"extra_rows": {"gdn_conv": 12288, "gate": 256}}),
        ("query_one", {"query_tokens": 1}),
        ("query_1024", {"query_tokens": 1024}),
        ("query_capacity_overflow", {"query_tokens": 1025}),
        ("kv_u16_max", {"kv_tokens": 65535}),
        ("kv_u16_overflow", {"kv_tokens": 65536}),
        ("kv_capacity_overflow", {"max_kv_tokens": 1024}),
        ("kv_shorter", {"kv_tokens": 2}),
        ("row_u16_max", {"ffn": 65535}),
        ("row_u16_overflow", {"ffn": 65536}),
        ("aligned16_max", {"ffn": 65520}),
        ("aligned32_max", {"head_dim": 16376}),
        ("derived_q_overflow", {"head_dim": 16384}),
        ("derived_context_overflow", {"value_dim": 16384}),
        ("extra_row_overflow", {"extra_rows": {"gate": 65536}}),
        ("invalid_group", {"q_heads": 3, "kv_heads": 2}),
        ("zero_heads", {"kv_heads": 0}),
        ("zero_tokens", {"query_tokens": 0}),
        ("negative_ffn", {"ffn": -16}),
        ("boolean_dimension", {"hidden": True}),
    ):
        add(name, "shape", shape, "candidate_only_not_current_frontend_acceptance", **change)

    legacy = dict(hidden=64, ffn=80, heads=2, kv_heads=1, head_dim=32, max_tokens=33)
    for name, change in (("legacy_tail", {}), ("legacy_tiny", {"ffn": 128, "max_tokens": 1024}),
                         ("legacy_qwen2", {"hidden": 1536, "ffn": 8960, "heads": 12, "kv_heads": 2,
                                           "head_dim": 128, "max_tokens": 1024}),
                         ("legacy_wide_product", {"hidden": 65504, "ffn": 65520, "heads": 2047,
                                                 "max_tokens": 1})):
        add(name, "legacy_layout", legacy, "safe_legacy_layout_arithmetic_only", **change)

    wide = dict(base=0, dims=[65535, 65535], byte_strides=[262140, 4], element_bytes=4,
                indices=[65534, 65534], address_bits=56, stride_bits=64, span_bits=64)
    for name, change in (
        ("wide_multiply_above_u32", {}),
        ("wide_high_base_above_exact_double", {"base": (1 << 55) + 64}),
        ("wide_u32_span_rejected", {"span_bits": 32}),
        ("wide_byte_stride_above_u32", {"dims": [3, 16], "byte_strides": [1 << 33, 4], "indices": [2, 15]}),
        ("wide_stride_field_overflow", {"dims": [3, 16], "byte_strides": [1 << 32, 4], "indices": [2, 15], "stride_bits": 32}),
        ("wide_span_multiply_overflow", {"dims": [65535, 1], "byte_strides": [1 << 63, 4], "indices": [65534, 0], "address_bits": 64}),
        ("wide_span_sum_overflow", {"dims": [3, 1], "byte_strides": [(1 << 63) - 1, 4], "indices": [2, 0], "address_bits": 64}),
        ("wide_payload_u64_overflow", {"dims": [65535]*4, "byte_strides": [65535**3*8, 65535**2*8, 65535*8, 8],
                                       "indices": [0]*4, "element_bytes": 8, "address_bits": 64}),
        ("wide_end_u64_exact", {"base": (1 << 64) - 64, "dims": [16], "byte_strides": [4], "indices": [15], "address_bits": 64}),
        ("wide_end_u64_overflow", {"base": (1 << 64) - 64, "dims": [17], "byte_strides": [4], "indices": [16], "address_bits": 64}),
        ("wide_padding_only_overflow", {"base": 0, "dims": [17], "byte_strides": [1], "indices": [16], "element_bytes": 1, "address_bits": 5}),
        ("wide_aperture_exact", {"base": (1 << 56) - 64, "dims": [16], "byte_strides": [4], "indices": [15]}),
        ("wide_aperture_overflow", {"base": (1 << 56) - 64, "dims": [17], "byte_strides": [4], "indices": [16]}),
        ("wide_base_overflow", {"base": 1 << 56}),
        ("wide_unaligned_base", {"base": 4}),
        ("wide_last_index_rejected", {"indices": [65535, 0]}),
        ("wide_overlap_rejected", {"byte_strides": [4, 4]}),
        ("wide_negative_stride", {"byte_strides": [-262140, 4]}),
        ("wide_rank4", {"dims": [3, 5, 7, 11], "byte_strides": [2240, 448, 64, 4], "indices": [2, 4, 6, 10]}),
    ):
        add(name, "wide_address", wide, "generic_byte_stride_stress_not_v2_wire", **change)

    tensor = dict(base=16384, dims=[1, 16, 1, 1], rank=2, strides=[16, 1, 1],
                  dtype=7, region_base=0, region_limit=1 << 56)
    for name, change in (
        ("v2_fp32", {}), ("v2_bf16", {"dtype": 5}),
        ("v2_region_base_unaligned", {"region_base": 1, "region_limit": 65536}),
        ("v2_region_limit_unaligned", {"region_base": 0, "region_limit": 65537}),
        ("v2_u32_elements_max", {"dims": [65535, 65537, 1, 1], "strides": [65537, 1, 1]}),
        ("v2_u32_elements_overflow", {"dims": [65536, 65536, 1, 1], "strides": [65536, 1, 1]}),
        ("v2_s24_stride_max", {"dims": [1, 47, 178481, 1], "rank": 3, "strides": [8388607, 178481, 1]}),
        ("v2_s24_stride_overflow", {"dims": [1, 2048, 4096, 1], "rank": 3, "strides": [8388608, 4096, 1]}),
        ("v2_negative_stride", {"strides": [-16, 1, 1]}),
        ("v2_malformed_stride", {"strides": [15, 1, 1]}),
        ("v2_inactive_dimension", {"dims": [1, 16, 2, 1]}),
        ("v2_u18_dimension_max", {"dims": [1, 262143, 1, 1], "strides": [262143, 1, 1]}),
        ("v2_u18_dimension_overflow", {"dims": [1, 262144, 1, 1], "strides": [262144, 1, 1]}),
        ("v2_aperture_exact", {"base": (1 << 56) - 64}),
        ("v2_aperture_overflow", {"base": (1 << 56) - 64, "dims": [1, 17, 1, 1], "strides": [17, 1, 1]}),
        ("v2_unaligned_payload_only_limit", {"dims": [1, 1, 1, 1], "strides": [1, 1, 1], "region_limit": 16388}),
        ("v2_padding_region_exact", {"dims": [1, 1, 1, 1], "strides": [1, 1, 1], "region_limit": 16448}),
    ):
        add(name, "tensor_v2", tensor, "current_reader_arithmetic_not_rtl_execution", **change)
    return result


def artifacts(root=ROOT):
    rows = cases()
    document = {"schema": "heteronpu.shape-layout-vectors.v1", "evidence_class": "synthetic_E0",
                "integer_encoding": "decimal_strings_no_float_conversion",
                "source_baseline_commit": "4ba43dce23e465796aa31cb9f1752516c7084ac8",
                "source_sha256": {p: hashlib.sha256((root/p).read_bytes()).hexdigest() for p in SOURCES},
                "chisel_consumer_executed": False, "rtl_executed": False,
                "official_checkpoint_verified": False, "vectors": wire(rows)}
    # No numeric JSON parser is needed by the actual legacy Scala consumer.
    lines = ["# C03.3 legacy-layout-v1: decimal integers; region triples name:offset:words:external"]
    for case in rows:
        if case["operation"] != "legacy_layout":
            continue
        i, o = case["inputs"], case["expected"]["result"]
        fields = [case["id"]] + [str(i[k]) for k in ("hidden", "ffn", "heads", "kv_heads", "head_dim", "max_tokens")]
        fields += [str(o[k]) for k in ("max_row", "kv_width", "writable_start", "total")]
        fields += [",".join(f'{r["name"]}:{r["offset"]}:{r["words"]}:{int(r["external"])}' for r in o["regions"])]
        lines.append("\t".join(fields))
    legacy_text = "\n".join(lines) + "\n"
    return {FIXTURE: json.dumps(document, indent=2, ensure_ascii=False) + "\n",
            LEGACY: legacy_text, SCALA_RESOURCE: legacy_text}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    for relative, content in artifacts(args.root).items():
        path = args.root / relative
        if args.check:
            if not path.is_file() or path.read_text() != content:
                raise SystemExit(f"STALE_VECTOR: {relative}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
    print(f"C03_3_VECTORS_{'CHECKED' if args.check else 'GENERATED'} cases={len(cases())}")


if __name__ == "__main__":
    main()
