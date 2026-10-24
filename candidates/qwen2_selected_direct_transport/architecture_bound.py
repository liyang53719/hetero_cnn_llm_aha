"""Exact, conditional architecture bound; not a simulator or timing measurement.

The source argument is an explicitly supplied fixture root. Its pinned manifest
identifies selected Scala postimages; raw main Scala is NOT a selected postimage.
This program verifies manifest identity, not elaboration or the Scala bodies.
"""

import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path


SOURCE_COMMIT = "1bdf70eb42de8752edeb616e8ef01e166628ca35"
SOURCE_TREE = "cc48abbc5e4fe59782e04feac3baa2057f300567"
POSTIMAGE_MANIFEST = (
    "candidates/qwen2_resident_matrix/production_qk16_rebase/POSTIMAGE_PINS.json"
)
POSTIMAGE_MANIFEST_SHA256 = (
    "f7b534e22e3d707129a00315343a71365ade205f0b0052a69593146e383659fb"
)
POSTIMAGE_MANIFEST_BYTES = 1351
SCALA = "chisel/continuous_prefill/src/main/scala/heteronpu/continuous/"
SELECTED_POSTIMAGES = {
    SCALA + "Qwen2Block.scala": "31b618680b4c750398a0dcf21fa34185dd9fc9b1732e370cfce502915814bd68",
    SCALA + "QwenOwnerProtocol.scala": "f14c7f27f65d9679ea1241607eede3bc26903ece4385e62317bf40d6dce963e3",
    SCALA + "MatrixPipeline.scala": "83516358916a6bb4a4816d700f056aae028c62dd0cc8891ea97f0cb9fea958cc",
    SCALA + "HostBlockTop.scala": "15cc34f041228f38d69b15868a9f9c45fb3f9ea53a9275ec6a6d9fd70b4b0c25",
    SCALA + "PackedAttentionStreamClient.scala": "58fb22a6f78a224241b9b0368e3108e5c403a9ea7106527061b140ff5d83b8c0",
}
CANONICAL_INPUTS = {
    "tokens": 128,
    "heads": 12,
    "head_dim": 128,
    "qk_pack": 16,
    "pv_columns_per_step": 16,
    "fixed_matrix_macs": 4096,
    "wide_normal_steps_per_service_clock": 1,
    "qk_steps": 55296,
    "pv_steps": 792576,
    "dense_useful_macs_per_token": 46792704,
    "full_block_useful_macs": 6014828544,
}


def _anchor(filename, first, last, claim, excerpt):
    return {
        "source_kind": "selected_scala_postimage",
        "path": SCALA + filename,
        "sha256": SELECTED_POSTIMAGES[SCALA + filename],
        "lines_inclusive": [first, last],
        "claim": claim,
        "excerpt": excerpt,
    }


# These are reviewed source anchors, not assertions that the fixture contains
# or compiles the selected bodies. Hashes disambiguate them from raw main files.
SOURCE_ANCHORS = [
    _anchor("QwenOwnerProtocol.scala", 131, 155,
            "One external Matrix service; legacy core and Dense use this service.",
            "val matrix=Module(new MatrixPipelineService(enableTransposedDense=enableTransposedDense,enableAccumulatorSeed=enableTransposedSeed,enablePackedDrainStatus=enableProductionPackedQk16))"),
    _anchor("QwenOwnerProtocol.scala", 486, 512,
            "Dense and legacy ready signals are exclusive and feed one step mux.",
            "matrix.io.port.step.valid:=Mux(useDense,dense.matrix.step.valid,legacy.io.port.step.valid)"),
    _anchor("QwenOwnerProtocol.scala", 517, 541,
            "Packed QK overrides that same port; legacy, Dense, and Dense seed handshakes are disabled.",
            "legacy.io.port.group.ready:=false.B;legacy.io.port.step.ready:=false.B\n"
            "dense.matrix.group.ready:=false.B;dense.matrix.step.ready:=false.B\n"
            "matrix.io.port.step.valid:=p.step.valid;matrix.io.port.step.bits:=p.step.bits"),
    _anchor("MatrixPipeline.scala", 65, 80,
            "Eight selected slices and five legal contexts share one normal step; contexts are not issue ports.",
            "val leaves=Seq.fill(8)(Module(new RetainedMatrixEndpoint(enableAccumulatorSeed)))\n"
            "val legalContext=x.context<5.U"),
    _anchor("MatrixPipeline.scala", 141, 167,
            "One payload fans out to selected slices on gated service clock; one legal step.fire enqueues metadata.",
            "gate.io.clk_i:=clock;gate.io.test_en_i:=false.B\n"
            "tags.io.enq.valid:=io.port.step.fire && legalStep"),
    _anchor("MatrixPipeline.scala", 192, 197,
            "Each legal accepted normal step increments wideSteps once, independent of active slice count.",
            "steps:=steps+PopCount(group.sliceMask);wideSteps:=wideSteps+1.U"),
    _anchor("MatrixPipeline.scala", 60, 63,
            "Groups enter only in idle; terminal done waits for returned values to retire.",
            "io.port.group.ready:=state===idle && !poison\n"
            "io.port.done.valid:=state===finish && !values.io.deq.valid"),
    _anchor("MatrixPipeline.scala", 178, 206,
            "The accepted group remains registered through completion; done.fire alone returns normal operation to idle.",
            "when(io.port.done.fire){state:=Mux(poison,locked,idle)}"),
    _anchor("PackedAttentionStreamClient.scala", 41, 59,
            "QK uses eight normal steps, context zero, opcode 0x23, and all eight slices.",
            "val finalIndex=Mux(descriptor.pv,descriptor.count-1.U,7.U)\n"
            "io.port.group.bits.sliceMask:=Mux(descriptor.pv,0x0f.U,0xff.U)"),
    _anchor("Qwen2Block.scala", 203, 220,
            "The selected packed client is QK only and holds ownership until completion.fire.",
            "c.io.start.bits.tag:=packedTag.get;c.io.start.bits.pv:=false.B;c.io.start.bits.count:=packedKeys\n"
            "when(c.io.completion.fire){packedOwned.get:=false.B}"),
    _anchor("Qwen2Block.scala", 179, 199,
            "Legacy PV uses opcode 0x24 and sliceMask=1; the one port cannot issue Dense on its seven inactive slices.",
            "matrixRequest.bits.opcode:=Mux(dot,0x23.U,Mux(pv,0x24.U,0x20.U))"),
    _anchor("Qwen2Block.scala", 579, 613,
            "Packed QK iterates depth 0..112 by 16 and causal key groups of at most sixteen.",
            "when(key+packedKeys<=token){key:=key+packedKeys;state:=st(\"attKey\")}"),
    _anchor("Qwen2Block.scala", 622, 630,
            "Legacy PV iterates all causal keys and eight sixteen-column chunks per head.",
            "when(key<token){key:=key+1.U;state:=st(\"attProbRead\")}.otherwise{state:=st(\"attPVWrite\")}"),
    _anchor("MatrixPipeline.scala", 216, 245,
            "Legacy requests become single normal stream steps, not another arithmetic engine.",
            "when(io.port.step.fire){state:=waitResult}"),
]


def architecture_bound(**overrides):
    """Return exact integers/Fractions for this canonical 128-token profile only.

    Reject changed geometry, resources, supplied work totals and issue counts.
    Dense/full-block useful work are GIVEN premises, not results of this program.
    """
    unknown = set(overrides) - set(CANONICAL_INPUTS)
    if unknown:
        raise ValueError("Unknown bound inputs: " + ", ".join(sorted(unknown)))
    inputs = dict(CANONICAL_INPUTS, **overrides)
    for key, value in inputs.items():
        if type(value) is not int or value != CANONICAL_INPUTS[key]:
            raise ValueError("Noncanonical bound input: " + key)
    n, h, d = inputs["tokens"], inputs["heads"], inputs["head_dim"]
    group_sum = sum((t + inputs["qk_pack"] - 1) // inputs["qk_pack"]
                    for t in range(1, n + 1))
    causal_pairs = n * (n + 1) // 2
    qk = h * (d // 16) * group_sum
    pv = h * (d // inputs["pv_columns_per_step"]) * causal_pairs
    if (qk, pv) != (inputs["qk_steps"], inputs["pv_steps"]):
        raise ValueError("Canonical attention issue count mismatch")
    dense = n * inputs["dense_useful_macs_per_token"]
    full = inputs["full_block_useful_macs"]
    if full - dense != 2 * h * d * causal_pairs:
        raise ValueError("Given useful work does not reconcile with causal QK/PV")
    capacity = inputs["fixed_matrix_macs"]
    dense_slots = (dense + capacity - 1) // capacity
    shared_slots = qk + pv + dense_slots
    denominator = capacity * shared_slots
    return {
        "inputs": inputs,
        "causal_pairs": causal_pairs,
        "qk_key_groups_per_head": group_sum,
        "qk_normal_issue_slots": qk,
        "pv_normal_issue_slots": pv,
        "attention_disjoint_normal_issue_slots": qk + pv,
        "dense_useful_macs_given": dense,
        "attention_useful_macs_reconciled": full - dense,
        "ideal_dense_normal_issue_slots_lower_bound": dense_slots,
        "hardware_service_clock_cycles_lower_bound": shared_slots,
        "fixed_4096_whole_block_capacity_denominator": denominator,
        "architecture_utilization_upper_bound": Fraction(full, denominator),
        "architecture_useful_macs_per_service_clock_upper_bound": Fraction(full, shared_slots),
    }


def _pin_map(rows):
    if not isinstance(rows, list) or len(rows) != 5:
        raise ValueError("Expected exactly five selected postimage pins")
    result = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "base_sha256", "post_sha256"}:
            raise ValueError("Malformed selected postimage pin")
        if row["path"] in result:
            raise ValueError("Duplicate selected postimage path")
        result[row["path"]] = row["post_sha256"]
    if result != SELECTED_POSTIMAGES:
        raise ValueError("Selected postimage hashes differ from this proof")
    return result


def verify_source_pins(source_root, input_pins_path=None):
    """Read only explicit fixture root plus adjacent input pins; never Scala bodies."""
    if source_root is None:
        raise ValueError("An explicit --source-root is required for fixture reads")
    source_root = Path(source_root)
    input_pins_path = (Path(input_pins_path) if input_pins_path is not None
                       else Path(__file__).with_name("INPUT_PINS.json"))
    inputs = json.loads(input_pins_path.read_bytes())
    if inputs.get("source_commit") != SOURCE_COMMIT or inputs.get("source_tree") != SOURCE_TREE:
        raise ValueError("INPUT_PINS source identity mismatch")
    _pin_map(inputs.get("selected_scala_postimages"))
    expected = {"bytes": POSTIMAGE_MANIFEST_BYTES, "sha256": POSTIMAGE_MANIFEST_SHA256}
    if inputs.get("sources", {}).get(POSTIMAGE_MANIFEST) != expected:
        raise ValueError("INPUT_PINS manifest identity mismatch")
    raw = (source_root / POSTIMAGE_MANIFEST).read_bytes()
    if len(raw) != POSTIMAGE_MANIFEST_BYTES or hashlib.sha256(raw).hexdigest() != POSTIMAGE_MANIFEST_SHA256:
        raise ValueError("Fixture POSTIMAGE_PINS byte identity mismatch")
    rows = json.loads(raw)
    _pin_map(rows)
    if rows != inputs["selected_scala_postimages"]:
        raise ValueError("Fixture and INPUT_PINS postimage records differ")
    return {
        "source_commit": SOURCE_COMMIT,
        "source_tree": SOURCE_TREE,
        "manifest_path_relative_to_source_root": POSTIMAGE_MANIFEST,
        "manifest_sha256": POSTIMAGE_MANIFEST_SHA256,
        "manifest_bytes": POSTIMAGE_MANIFEST_BYTES,
        "selected_scala_postimages": rows,
        "verification_scope": "Pinned manifest bytes and declared selected identities only; selected Scala bodies are not read or compiled.",
        "selected_postimage_bodies_verified_by_this_program": False,
        "raw_main_scala_used_as_selected_postimage": False,
    }


def _json_exact(value):
    if isinstance(value, Fraction):
        return {"numerator": value.numerator, "denominator": value.denominator}
    if isinstance(value, dict):
        return {key: _json_exact(item) for key, item in value.items()}
    return value


def evidence(source_root):
    return {
        "schema": 1,
        "claim_kind": "conditional_fixed_resource_architecture_upper_bound",
        "not_measured_utilization": True,
        "not_predicted_runtime": True,
        "python_scheduler_ticks_used_as_hardware_cycles": False,
        "native_rtl_eda_or_ci_validation": False,
        "premises": [
            "Canonical 128-token Qwen2 profile, selected packed QK16 plus legacy PV.",
            "Given Dense useful work: 128 * 46792704 MACs; given full-block useful work: 6014828544 MACs.",
            "Fixed physical Matrix capacity is 4096 MACs, with at most one wide normal step per service clock.",
            "All given Dense Matrix work uses that shared normal-step issue resource; no extra arithmetic engine is assumed.",
            "A Dense issue is optimistically granted up to 4096 useful MACs; seed transfers do not replace required Dense products.",
        ],
        "proof": [
            "QK and PV require 55296 + 792576 = 847872 distinct shared-port normal issue slots.",
            "Dense requires ceil(5989466112 / 4096) = 1462272 additional disjoint normal issue slots.",
            "At most one such issue per service clock implies C >= 2310144, independently of any Python model ticks.",
            "The whole-block denominator is 4096 * C, not active slices or a Dense-only interval.",
            "U <= 6014828544 / (4096 * 2310144) = 30593/48128 exactly.",
        ],
        "limitations": [
            "This is an optimistic upper bound, not sustained one-step-per-cycle attainability.",
            "Command, operand gathering, seed, memory, scalar, result and drain overheads are omitted.",
            "Issue-slot exclusivity does not assert that all DDR, scalar or internal pipeline activity is nonoverlapping.",
            "Selected source limits packed Attention to m <= 128 at Qwen2Block.scala:345; no longer-sequence claim is made.",
            "Manifest regression is not source elaboration, selected-body reconstruction, functional or numerical validation.",
        ],
        "source_identity": verify_source_pins(source_root),
        "reviewed_selected_source_anchors": SOURCE_ANCHORS,
        "exact_bound": _json_exact(architecture_bound()),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path,
                        help="Explicit fixture/repository root containing the pinned POSTIMAGE_PINS.json")
    args = parser.parse_args()
    print(json.dumps(evidence(args.source_root), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
