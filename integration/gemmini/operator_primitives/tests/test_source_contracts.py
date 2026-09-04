from __future__ import annotations

from pathlib import Path
import re

import yaml

from reference.operator_primitives_reference import (
    COMPOSITE_LEAF_SEQUENCES, MODEL_OPERATOR_ROOT_OPCODE_SEQUENCES,
    MODEL_REQUIRED_OPERATORS, OPERATOR_PHASE_COUNTS, TERMINAL_PRIMITIVE_BINDINGS,
    TERMINAL_PRIMITIVE_OWNERS,
)

PACKAGE = Path(__file__).resolve().parents[1]
SCALA = PACKAGE / "src" / "main" / "scala" / "gemmini"
REPO = PACKAGE.parents[2]


def strip_scala(text: str) -> str:
    """Remove comments and strings while preserving delimiters/newlines."""
    out: list[str] = []
    index = 0
    state = "code"
    block_depth = 0
    while index < len(text):
        c = text[index]
        n = text[index + 1] if index + 1 < len(text) else ""
        if state == "code":
            if c == "/" and n == "/":
                out.extend("  ")
                index += 2
                state = "line"
            elif c == "/" and n == "*":
                out.extend("  ")
                index += 2
                state = "block"
                block_depth = 1
            elif c == '"':
                out.append(" ")
                index += 1
                state = "string"
            else:
                out.append(c)
                index += 1
        elif state == "line":
            if c == "\n":
                out.append("\n")
                state = "code"
            else:
                out.append(" ")
            index += 1
        elif state == "block":
            if c == "/" and n == "*":
                out.extend("  ")
                index += 2
                block_depth += 1
            elif c == "*" and n == "/":
                out.extend("  ")
                index += 2
                block_depth -= 1
                if block_depth == 0:
                    state = "code"
            else:
                out.append("\n" if c == "\n" else " ")
                index += 1
        else:
            if c == "\\" and n:
                out.extend("  ")
                index += 2
            elif c == '"':
                out.append(" ")
                index += 1
                state = "code"
            else:
                out.append("\n" if c == "\n" else " ")
                index += 1
    assert state in {"code", "line"}
    return "".join(out)


def test_scala_delimiters_are_balanced() -> None:
    pairs = {"}": "{", ")": "(", "]": "["}
    for path in sorted(SCALA.glob("*.scala")):
        stack: list[tuple[str, int]] = []
        for position, char in enumerate(strip_scala(path.read_text())):
            if char in "{([":
                stack.append((char, position))
            elif char in "})]":
                assert stack, (path, position, char)
                opening, opening_position = stack.pop()
                assert opening == pairs[char], (path, opening_position, position)
        assert not stack, (path, stack[-5:])


def test_no_incomplete_markers_or_runtime_dividers() -> None:
    for path in sorted(SCALA.glob("*.scala")):
        text = path.read_text()
        assert not re.search(r"\b(?:TODO|FIXME)\b|\?\?\?", text), path
        code = strip_scala(text)
        # Chisel inequality is =/=; exclude it. Constant modulo is not used in
        # these controllers either, so any arithmetic / or % is a review gate.
        assert not re.search(r"(?<![=/])/([^=*/]|$)", code), path
        assert "%" not in code, path


def test_topk_and_large_state_are_memory_or_external_state_based() -> None:
    selection = (SCALA / "HeteroSelectionMemoryPrimitives.scala").read_text()
    state = (SCALA / "HeteroStatePrimitives.scala").read_text()
    assert "SyncReadMem(maxK" in selection
    assert "maxK: Int = 512" in selection
    assert re.search(r"maxChannels:\s*Int\s*=\s*16384", state)
    assert "historyReadAddress" in state and "historyWriteAddress" in state
    assert "Reg(Vec(maxChannels" not in state


def test_model_ids_counts_and_decode_are_complete() -> None:
    protocol = (SCALA / "HeteroOperatorPrimitiveProtocol.scala").read_text()
    sequencer = (SCALA / "HeteroModelOperatorSequencer.scala").read_text()
    id_block = protocol.split("object HeteroModelOperatorId", 1)[1].split("class HeteroOperatorCommand", 1)[0]
    ids = set(re.findall(r"val\s+([A-Za-z0-9_]+)\s*=", id_block)) - {"width"}
    assert ids == set(OPERATOR_PHASE_COUNTS)
    count_matches = dict(
        (name, int(count))
        for name, count in re.findall(
            r"is\(HeteroModelOperatorId\.([A-Za-z0-9_]+)\)\s*\{\s*count\s*:=\s*(\d+)\.U",
            sequencer,
        )
    )
    assert count_matches == OPERATOR_PHASE_COUNTS
    for name in ids:
        # One occurrence in countFor and at least one in the decode switch.
        assert sequencer.count(f"is(HeteroModelOperatorId.{name})") >= 2, name
    assert "assert(op.opcode =/= HeteroPrimitiveOpcode.Nop)" in sequencer
    assert "requestedCount === 0.U" in sequencer


def test_root_sequence_reference_is_complete_and_leaf_bound() -> None:
    assert set(MODEL_OPERATOR_ROOT_OPCODE_SEQUENCES) == set(OPERATOR_PHASE_COUNTS)
    for operator, sequence in MODEL_OPERATOR_ROOT_OPCODE_SEQUENCES.items():
        assert len(sequence) == OPERATOR_PHASE_COUNTS[operator]
        for opcode in sequence:
            if opcode == "StateCommitOrRollback":
                assert {"StateCommit", "StateRollback"} <= TERMINAL_PRIMITIVE_BINDINGS
            elif opcode in COMPOSITE_LEAF_SEQUENCES:
                assert set(COMPOSITE_LEAF_SEQUENCES[opcode]) <= TERMINAL_PRIMITIVE_BINDINGS
            else:
                assert opcode in TERMINAL_PRIMITIVE_BINDINGS, (operator, opcode)


def test_catalog_covers_every_new_controller() -> None:
    catalog = (SCALA / "EmitHeteroOperatorPrimitiveCatalog.scala").read_text()
    expected = {
        "unsigned_divide", "unsigned_multiply", "streaming_topk",
        "tagged_gather_reorder", "moe_route_dispatch", "ple_ngram_hash",
        "qsa_block_selector", "causal_conv_address", "gdn_state_address",
        "norm_address", "gated_residual_address", "state_transaction",
        "mtp_verify", "composite_activation", "primitive_capability_decode",
        "primitive_leaf_expander",
        "terminal_model_operator_frontend", "fp32_pwl_segment_search",
        "block_pool_address", "mrope_section_map", "vision_window_address",
        "vision_patch_merge_address", "vision_bilinear_index",
        "vision_patch3d_address", "model_operator_sequencer",
    }
    listed = set(re.findall(r'^\s*"([a-z0-9_]+)",?\s*$', catalog, re.MULTILINE))
    assert listed == expected
    for name in expected:
        assert f'case "{name}" =>' in catalog


def test_synthesizable_capability_registry_guards_both_boundaries() -> None:
    capability = (SCALA / "HeteroPrimitiveCapability.scala").read_text()
    sequencer = (SCALA / "HeteroModelOperatorSequencer.scala").read_text()
    leaf = (SCALA / "HeteroPrimitiveLeafExpander.scala").read_text()
    for owner in ("Control", "Dma", "Matrix", "Sfu", "KvMemory", "State", "Selection", "Vision"):
        assert f"HeteroPrimitiveOwner.{owner}" in capability
    assert "HeteroPrimitiveCapability.source(op.owner, op.opcode)" in sequencer
    assert "HeteroPrimitiveCapability.terminal(" in leaf
    assert "PopCount" in capability


def test_composite_opcodes_are_closed_by_terminal_leaf_expander() -> None:
    protocol = (SCALA / "HeteroOperatorPrimitiveProtocol.scala").read_text()
    leaf = (SCALA / "HeteroPrimitiveLeafExpander.scala").read_text()
    composite = {"SfuExp", "SfuSigmoid", "SfuSoftplus", "SfuSilu", "SfuGelu"}
    for opcode in composite:
        assert f"HeteroPrimitiveOpcode.{opcode}" in leaf
    assert "assert(!HeteroCompositeOpcode.isComposite" in leaf
    assert "parentOpcode" in leaf and "parentVariant" in leaf
    assert "scratchValid" in leaf and "scratchSrc0" in leaf and "scratchDst" in leaf
    assert "terminal_model_operator_frontend" in (SCALA / "EmitHeteroOperatorPrimitiveCatalog.scala").read_text()
    # Composite ids remain architectural source opcodes, but no composite is
    # permitted at the terminal executor boundary.
    for opcode in composite:
        assert f"val {opcode}" in protocol


def test_coverage_manifest_has_zero_missing_operators() -> None:
    manifest = yaml.safe_load((PACKAGE / "operator_coverage_800mhz.yaml").read_text())
    assert manifest["status"] == "PASS_OPERATOR_PRIMITIVE_COVERAGE"
    assert manifest["clock"]["target_hz"] == 800_000_000
    for key, required in MODEL_REQUIRED_OPERATORS.items():
        model = manifest["models"][key]
        assert model["missing"] == []
        assert set(model["required_model_operators"]) == set(required)
        assert model["coverage"] == "complete_at_chisel_operator_primitive_layer"


def test_800mhz_policy_contains_no_active_1ghz_target() -> None:
    clock = yaml.safe_load((REPO / "configs" / "global_clock_800mhz.yaml").read_text())
    assert clock["target_hz"] == 800_000_000
    assert clock["period_ns"] == 1.25
    for path in (
        REPO / "configs" / "arch_v0.yaml",
        REPO / "configs" / "arch_v1.yaml",
        REPO / "configs" / "arch_v2_qwen38_candidate.yaml",
        REPO / "dc" / "operator_primitives_800mhz.tcl",
    ):
        text = path.read_text()
        assert "1000000000" not in text
        assert "-period 1.0" not in text


def test_terminal_binding_manifest_matches_synthesizable_registry() -> None:
    binding = yaml.safe_load((PACKAGE / "terminal_primitive_bindings_800mhz.yaml").read_text())
    flattened = {}
    for owner, provider in binding["providers"].items():
        for opcode in provider["opcodes"]:
            assert opcode not in flattened
            flattened[opcode] = owner
    assert flattened == TERMINAL_PRIMITIVE_OWNERS
    capability = (SCALA / "HeteroPrimitiveCapability.scala").read_text()
    for opcode, owner in flattened.items():
        assert f"HeteroPrimitiveOpcode.{opcode}" in capability
        assert f"HeteroPrimitiveOwner.{owner}" in capability


def test_qsa_and_block_pool_avoid_runtime_wide_address_products() -> None:
    selection = strip_scala((SCALA / "HeteroSelectionMemoryPrimitives.scala").read_text())
    qsa = selection.split("class HeteroQsaBlockSelector", 1)[1].split("class HeteroMultiplyResult", 1)[0]
    assert "HeteroUnsignedMultiply" in qsa
    assert not re.search(r"\b(?:block|blocks)\s*\*\s*ratio\b", qsa)
    sfu = strip_scala((SCALA / "HeteroSfuControlPrimitives.scala").read_text())
    pool = sfu.split("class HeteroBlockPoolAddressGenerator", 1)[1]
    assert "blockTokenBase + within" in pool
    assert "blockTokenBase := blockTokenBase + ratio" in pool
    assert pool.count("blockTokenBase := 0.U") >= 2


def test_terminal_micro_op_preserves_parent_phase_and_variant() -> None:
    leaf = (SCALA / "HeteroPrimitiveLeafExpander.scala").read_text()
    assert "val parentPhase = UInt(8.W)" in leaf
    assert "terminal.parentPhase := base.phase" in leaf
    assert "terminal.parentVariant := base.variant" in leaf


def test_same_cycle_gather_response_is_not_false_protocol_error() -> None:
    source = (SCALA / "HeteroSelectionMemoryPrimitives.scala").read_text()
    assert "val justAllocated=io.in.fire&&io.memResp.bits.slot===alloc" in source
    assert "valid(io.memResp.bits.slot)||justAllocated" in source


def test_generation_flow_records_provenance_and_never_cleans_outputs() -> None:
    script = (PACKAGE / "scripts" / "generate_all_primitives.sh").read_text()
    for token in (
        "repository_commit=", "gemmini_commit=", "java_version_begin",
        "sbt_version_begin", "chisel_source_sha256.txt",
        "contract_sha256.txt", "rtl_generation_audit.json",
    ):
        assert token in script
    assert not re.search(r"(?m)(?:^|[;&|]\s*)rm(?:\s|$)|git\s+clean|find\s+[^\n]*-delete", script)
    assert "test -s" in script
    assert "verify_generated_rtl.py" in script
