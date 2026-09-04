#!/usr/bin/env python3
"""Independent source/coverage audit for the three-model Chisel primitive gate.

This script intentionally does not claim generated-RTL or numerical-RTL
closure.  It proves that the canonical inventory is granular, every required
operator is bound in the Chisel catalog, every independently schedulable root
exists, critical model-specific semantic chains are present, and all active
clock inputs use the 800 MHz policy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "chisel" / "three_model_operator_primitives"
SCALA = PROJECT / "src" / "main" / "scala" / "heteronpu" / "operator"
INVENTORY_PATH = ROOT / "config" / "model_operator_inventory_v3_complete.json"
CLOCK_PATH = ROOT / "config" / "clock_policy_800mhz.json"
REPORT_PATH = ROOT / "reports" / "execution" / "OPERATOR_PRIMITIVE_COVERAGE_V3.json"

EXPECTED_ROOTS = {
    "HeteroTokenEmbeddingPrimitiveV3",
    "HeteroQwen2DecoderBlockPrimitiveV3",
    "HeteroQwen35DenseAttentionPrimitiveV3",
    "HeteroGatedDeltaNetPrimitiveV3",
    "HeteroMoePrimitiveV3",
    "HeteroQwen38GatedResidualReadPrimitiveV3",
    "HeteroQwen38GatedResidualWritePrimitiveV3",
    "HeteroPlePrimitiveV3",
    "HeteroQsaPrimitiveV3",
    "HeteroQwen38FinalHyperMergePrimitiveV3",
    "HeteroVisionPatchEmbedPrimitiveV3",
    "HeteroVisionTransformerBlockPrimitiveV3",
    "HeteroVisionPatchMergePrimitiveV3",
    "HeteroMultimodalInjectPrimitiveV3",
    "HeteroFinalNormPrimitiveV3",
    "HeteroLmHeadArgmaxPrimitiveV3",
    "HeteroMtpDraftPrimitiveV3",
    "HeteroMtpVerifyResolvePrimitiveV3",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _flatten_model(entry: dict[str, Any]) -> list[str]:
    if "required_operators" in entry:
        values = list(entry["required_operators"])
    else:
        values = [op for group in entry["required_groups"].values() for op in group]
    if len(values) != len(set(values)):
        duplicates = sorted({x for x in values if values.count(x) > 1})
        raise AssertionError(f"duplicate operators: {duplicates}")
    return values


def _ordered(text: str, tokens: list[str]) -> bool:
    cursor = 0
    for token in tokens:
        cursor = text.find(token, cursor)
        if cursor < 0:
            return False
        cursor += len(token)
    return True


def audit(generated: Path | None = None) -> dict[str, Any]:
    inventory = json.loads(_read(INVENTORY_PATH))
    clock = json.loads(_read(CLOCK_PATH))
    scala_files = sorted(SCALA.glob("*.scala"))
    assert scala_files, f"no Scala sources under {SCALA}"
    scala_text = "\n".join(_read(path) for path in scala_files)
    catalog_text = _read(SCALA / "Catalog.scala")
    text_programs = _read(SCALA / "ProgramsText.scala")
    q38_programs = _read(SCALA / "ProgramsQwen38.scala")
    vision_programs = _read(SCALA / "ProgramsVisionMtp.scala")
    protocol = _read(SCALA / "Protocol.scala")

    model_operators = {
        model: _flatten_model(entry)
        for model, entry in inventory["models"].items()
    }
    expected_counts = {model: len(ops) for model, ops in model_operators.items()}
    assert expected_counts == {
        "qwen2_1p5b": 30,
        "qwen3_5_35b_a3b": 93,
        "qwen3_8_flash_next": 150,
    }, expected_counts

    missing_catalog_strings = {
        model: [op for op in ops if f'"{op}"' not in catalog_text]
        for model, ops in model_operators.items()
    }
    assert all(not values for values in missing_catalog_strings.values()), missing_catalog_strings

    root_specs = set(re.findall(r'RootSpec\("([A-Za-z0-9_]+)"', catalog_text))
    root_classes = set(re.findall(r'class\s+(Hetero[A-Za-z0-9_]+PrimitiveV3)', scala_text))
    assert root_specs == EXPECTED_ROOTS, {
        "missing": sorted(EXPECTED_ROOTS - root_specs),
        "extra": sorted(root_specs - EXPECTED_ROOTS),
    }
    assert EXPECTED_ROOTS <= root_classes, sorted(EXPECTED_ROOTS - root_classes)

    # Sequencer protocol contract.
    for marker in (
        "val launch = Flipped(Decoupled",
        "val microOp = Decoupled",
        "val completion = Flipped(Decoupled",
        "val result = Decoupled",
        "tagMismatch",
        "phaseMismatch",
        "program.last.flags",
    ):
        assert marker in protocol, marker

    # Qwen2 complete decoder chain.
    assert _ordered(text_programs, [
        "val Qwen2DecoderBlock", "RmsNorm", "MatrixGemm", "Rope",
        "KvAppend", "KvGather", "MatrixQk", "ApplyMask",
        "OnlineSoftmax", "MatrixPv", "RmsNorm", "Silu",
        "VectorMul", "MatrixGemm", "VectorAdd", "StateCommit",
    ])

    # GDN exact recurrence and runtime-selectable Qwen3.8 gate.
    for marker in (
        "val GatedDeltaNet", "DepthwiseConv", "L2Norm", "Softplus",
        "Exp2", "MatrixOuter", "MatrixGemv", "ConfiguredGateAct",
        "StateCommit",
    ):
        assert marker in text_programs, marker
    assert text_programs.count("MicroOpTemplate(Exp2") >= 2
    assert text_programs.count("MicroOpTemplate(L2Norm") >= 2
    assert text_programs.count("MicroOpTemplate(MatrixGemv") >= 3

    # Hyper read must contain the previously missing down/scale/SiLU/up/sigmoid chain.
    assert _ordered(q38_programs, [
        "val GatedResidualRead", "GroupRmsNorm", "MatrixGemm",
        "Reciprocal", "VectorMul", "Silu", "MatrixGemm",
        "Sigmoid", "VectorMul", "ReduceSum",
    ])
    assert _ordered(q38_programs, [
        "val GatedResidualWrite", "GroupRmsNorm", "MatrixGemm",
        "Silu", "MatrixGemm", "Sigmoid", "VectorBroadcast",
        "VectorMul", "VectorAdd", "StateWrite", "StateCommit",
    ])
    assert "HeteroQwen38GatedResidualReadPrimitiveV3" in q38_programs
    assert "HeteroQwen38GatedResidualWritePrimitiveV3" in q38_programs

    # PLE and QSA are not accepted as coarse placeholders.
    assert _ordered(q38_programs, [
        "val Ple", "VectorCompare", "VectorSelect", "NgramHash",
        "DmaRead", "EmbeddingLookup", "SignedSqrt", "DepthwiseConv",
        "StateCommit",
    ])
    assert _ordered(q38_programs, [
        "val Qsa", "L2Norm", "ReduceSum", "Reciprocal", "MatrixQk",
        "VectorCompare", "StableTopK", "StableSort", "SparseGatherRun",
        "KvGather", "KvAppend", "OnlineSoftmax", "MatrixPv", "StateCommit",
    ])

    # Full vision and multimodal boundaries, not one vision_encoder binding.
    assert "vision_encoder" not in json.dumps(inventory)
    for marker in (
        "VisionPatchEmbed", "MatrixConv", "BilinearPosition",
        "VisionTransformerBlock", "LayerNorm", "NonCausal",
        "Gelu", "VisionPatchMerge", "SpatialMerge",
        "MultimodalInject", "MultimodalScatter",
        "MtpDraft", "MtpVerifyResolve", "StateResolve",
    ):
        assert marker in vision_programs, marker

    # Input embedding, final normalization/head and MTP resolve must remain separable roots.
    for root in (
        "HeteroTokenEmbeddingPrimitiveV3",
        "HeteroFinalNormPrimitiveV3",
        "HeteroLmHeadArgmaxPrimitiveV3",
        "HeteroMtpDraftPrimitiveV3",
        "HeteroMtpVerifyResolvePrimitiveV3",
    ):
        assert root in root_specs

    # Active clock gate.
    assert clock["target_clock_hz"] == 800_000_000
    assert clock["target_clock_mhz"] == 800
    assert abs(clock["target_period_ns"] - 1.25) < 1e-12
    active_clock_files = [
        ROOT / "configs" / "arch_v0.yaml",
        ROOT / "configs" / "arch_v1.yaml",
        ROOT / "configs" / "arch_v2_qwen38_candidate.yaml",
        ROOT / "dc" / "common_clock_800mhz.tcl",
    ]
    clock_text = "\n".join(_read(path) for path in active_clock_files)
    assert "target_hz: 1000000000" not in clock_text
    assert "clock_hz: 1000000000" not in clock_text
    assert "-period 1.0" not in clock_text
    assert "800000000" in clock_text and "1.250" in clock_text

    generated_result: dict[str, Any] = {"checked": False}
    if generated is not None:
        sv_files = sorted(generated.glob("*.sv"))
        manifest = generated / "MANIFEST.txt"
        coverage = generated / "OPERATOR_COVERAGE.csv"
        source_gate = generated / "SOURCE_GATE.txt"
        assert len(sv_files) == len(EXPECTED_ROOTS), [p.name for p in sv_files]
        assert manifest.is_file() and coverage.is_file() and source_gate.is_file()
        assert "PASS_CHISEL_OPERATOR_SOURCE_GATE" in _read(source_gate)
        generated_result = {
            "checked": True,
            "sv_count": len(sv_files),
            "sv_files": [p.name for p in sv_files],
            "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
            "coverage_sha256": hashlib.sha256(coverage.read_bytes()).hexdigest(),
        }

    payload = {
        "schema_version": 3,
        "status": "PASS_COMPLETE_THREE_MODEL_CHISEL_OPERATOR_PRIMITIVE_SOURCE_GATE",
        "evidence_boundary": inventory["evidence_boundary"],
        "target_clock_hz": clock["target_clock_hz"],
        "target_period_ns": clock["target_period_ns"],
        "root_count": len(EXPECTED_ROOTS),
        "operator_counts": expected_counts,
        "missing_operators": missing_catalog_strings,
        "generated": generated_result,
        "source_sha256": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in scala_files
        },
        "non_claims": [
            "no generated-RTL numerical closure is claimed by this source gate",
            "no integrated Command128/descriptor/L2 payload closure is claimed",
            "no DC timing, area or power closure is claimed",
        ],
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generated", type=Path)
    parser.add_argument("--output", type=Path, default=REPORT_PATH)
    args = parser.parse_args()
    payload = audit(args.generated)
    if args.output != REPORT_PATH:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
