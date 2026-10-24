"""Necessary QK Scalar lower bound, separate from the reviewed Matrix layer.

This is integer/Fraction reasoning over reviewed Scala states, not a simulator.
Matrix and Scalar lower bounds combine with MAX, allowing all cross-resource
overlap. Given full-block useful MACs stay over the fixed 4096-MAC denominator.
"""

import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
SCALA = "chisel/continuous_prefill/src/main/scala/heteronpu/continuous/"
BLOCKFLOAT_PATH = SCALA + "BlockFloat.scala"
BLOCKFLOAT_SHA256 = "9863718ca90089bf812eb07dbd82ce16d982a8c74b04d7543de1bd2dfb1e37b5"
BLOCKFLOAT_GIT_BLOB = "021c878dcb1106335d8a0cf768fdb862ab00533c"
BLOCKFLOAT_BYTES = 8313
QWEN2BLOCK_SHA256 = "31b618680b4c750398a0dcf21fa34185dd9fc9b1732e370cfce502915814bd68"
SOURCE_COMMIT = "1bdf70eb42de8752edeb616e8ef01e166628ca35"
SOURCE_TREE = "cc48abbc5e4fe59782e04feac3baa2057f300567"
IDENTITY_PROOF_SHA256 = "b1d1e1beb464316958923862f87b00b33a13440dfff294d0a5f7968ee63a3bb0"
SCALAR_PINS_SHA256 = "40cd67da2fb81ffb85452c83e0be40230a1f8ad2e4f690a1d762d83d2cb77f7f"
SCALAR_PINS_BYTES = 773
CANONICAL_INPUTS = {
    "tokens": 128,
    "heads": 12,
    "qk_adds_per_score": 16,
    "qk_scale_muls_per_score": 1,
    "scalar_acceptance_spacing_lower_bound": 3,
    "scalar_acceptance_to_result_spacing_lower_bound": 2,
    "fixed_matrix_macs": 4096,
    "full_block_useful_macs_given": 6014828544,
    "matrix_layer1_cycles_lower_bound": 2310144,
}


def _anchor(filename, first, last, claim, excerpt):
    is_blockfloat = filename == "BlockFloat.scala"
    return {
        "path": SCALA + filename,
        "source_kind": "unchanged_current_main_dependency" if is_blockfloat else "selected_scala_postimage",
        "sha256": BLOCKFLOAT_SHA256 if is_blockfloat else QWEN2BLOCK_SHA256,
        "lines_inclusive": [first, last],
        "claim": claim,
        "excerpt": excerpt,
    }


SOURCE_ANCHORS = [
    _anchor("Qwen2Block.scala", 103, 107,
            "One local BlockScalarFloat Module inherits the Qwen2 core implicit clock; no clock override occurs in the reviewed selected body.",
            "val scalar=Module(new BlockScalarFloat(enableSoftplus=enableGdnSoftplus));scalar.io.request.valid:=state===st(\"scalarReq\");scalar.io.request.bits:=scalarRequest;scalar.io.result.ready:=state===st(\"scalarRsp\")"),
    _anchor("Qwen2Block.scala", 301, 301,
            "Each calc call stores an operation and enters the request state for that one local Scalar.",
            "def calc(op:Int,a:UInt,b:UInt,next:String):Unit={scalarRequest.op:=op.U;scalarRequest.a:=a;scalarRequest.b:=b;scalarResume:=st(next);state:=st(\"scalarReq\")}"),
    _anchor("Qwen2Block.scala", 333, 334,
            "The core waits for request.fire and then result.fire; errors fail rather than complete the block successfully.",
            "when(state===st(\"scalarReq\")&&scalar.io.request.fire){state:=st(\"scalarRsp\")}"),
    _anchor("Qwen2Block.scala", 335, 356,
            "Owner tokens are j.m; Attention enters attQLoad after token/head/key/lane initialization. Packed Attention rejects m above 128.",
            "base:=0.U;tokens:=j.m;epoch:=j.tag(31,16)\n"
            "token:=0.U;head:=0.U;key:=0.U;depth:=0.U;col:=0.U;sum:=0.U;lane:=0.U;clearAcc()"),
    _anchor("Qwen2Block.scala", 153, 153,
            "Each causal packed key group has at most sixteen actual keys, including its tail.",
            "val packedKeys=Mux(token-key>=15.U,16.U(5.W),(token-key+1.U)(4,0))"),
    _anchor("Qwen2Block.scala", 579, 589,
            "Both the first packed score and every selected subsequent score initialize lane zero and positive-zero sum; no first-add bypass.",
            "when(depth===112.U){acc:=fmOut;lane:=0.U;sum:=0.U;state:=st(\"attReduce\")}\n"
            ".otherwise{acc:=selected;lane:=0.U;sum:=0.U;state:=st(\"attReduce\")}"),
    _anchor("Qwen2Block.scala", 594, 599,
            "Each score executes Add at lane 0 through lane 15, then a strict ScalarOp.Mul scaling operation.",
            "when(state===st(\"attReduce\")){calc(ScalarOp.Add,sum,acc(lane),\"attReduceDone\")}\n"
            "when(state===st(\"attReduceDone\")){sum:=scalarValue;when(lane===15.U){\n"
            ".otherwise{calc(ScalarOp.Mul,dotValue,F32.lit(1/math.sqrt(s.headDim.toDouble)),\"attScore\")}"),
    _anchor("Qwen2Block.scala", 600, 613,
            "Every actual causal key score is committed before advancing packed selection/groups; no padded keys are counted as scores.",
            "when(packedSelected.get+&1.U<packedKeys){\n"
            "when(key+packedKeys<=token){key:=key+packedKeys;state:=st(\"attKey\")}"),
    _anchor("Qwen2Block.scala", 558, 560,
            "Q-cache loading finishes by resetting causal key to zero for each head/token.",
            "when(state===st(\"attQStored\")){when(depth+16.U<s.headDim.U){depth:=depth+16.U;state:=st(\"attQLoad\")}.otherwise{key:=0.U;maxScore:=\"hff800000\".U;state:=st(\"attKey\")}}"),
    _anchor("Qwen2Block.scala", 630, 630,
            "After PV output, the loop advances all heads then tokens and reenters attQLoad.",
            ".elsewhen(head+1.U<s.heads.U){head:=head+1.U;depth:=0.U;state:=st(\"attQLoad\")}.elsewhen(token+1.U<tokens){token:=token+1.U;head:=0.U;depth:=0.U;state:=st(\"attQLoad\")}"),
    _anchor("BlockFloat.scala", 2, 17,
            "Same heteronpu.continuous package; ScalarOp.Add=0 and Mul=1 bind to this implementation, which imports gemmini.HeteroFP32Alu.",
            "package heteronpu.continuous\nimport gemmini.HeteroFP32Alu\n"
            "val Add=0;val Mul=1;val Div=2;val Sqrt=3;val ExpNegative=4"),
    _anchor("BlockFloat.scala", 32, 55,
            "BlockScalarFloat is a clocked Module with registered state and one HeteroFP32Alu; ready only idle and result valid only done.",
            "class BlockScalarFloat(enableSoftplus: Boolean = false) extends Module {\n"
            "val alu=Module(new HeteroFP32Alu);alu.io.op:=false.B;alu.io.x:=a;alu.io.y:=b\n"
            "io.request.ready:=state===idle;io.result.valid:=state===done;io.result.bits:=out;io.error:=err"),
    _anchor("BlockFloat.scala", 58, 81,
            "A successful finite Add/Mul captures in idle, goes to normal, registers the ALU result, then enters done.",
            "is(idle){when(io.request.fire){a:=io.request.bits.a;b:=io.request.bits.b;op:=io.request.bits.op;err:=false.B\n"
            ".elsewhen(io.request.bits.op===ScalarOp.Div.U || io.request.bits.op===ScalarOp.Sqrt.U){state:=divIssue}.otherwise{state:=normal}\n"
            "is(normal){\nalu.io.op:=op===ScalarOp.Mul.U || op===ScalarOp.MulIeeeRne.U\n"
            "out:=alu.io.out\nstate:=done"),
    _anchor("BlockFloat.scala", 108, 108,
            "Only result.fire in done returns to idle; same-edge result and next request cannot both fire.",
            "is(done){when(io.result.fire){state:=idle}}"),
]


def scalar_bound(**overrides):
    """Return exact necessary bounds for the canonical successful M128 block."""
    unknown = set(overrides) - set(CANONICAL_INPUTS)
    if unknown:
        raise ValueError("Unknown scalar-bound inputs: " + ", ".join(sorted(unknown)))
    inputs = dict(CANONICAL_INPUTS, **overrides)
    for name, value in inputs.items():
        if type(value) is not int or value != CANONICAL_INPUTS[name]:
            raise ValueError("Noncanonical scalar-bound input: " + name)
    scores = inputs["heads"] * inputs["tokens"] * (inputs["tokens"] + 1) // 2
    adds = scores * inputs["qk_adds_per_score"]
    muls = scores * inputs["qk_scale_muls_per_score"]
    operations = adds + muls
    scalar_span = ((operations - 1) * inputs["scalar_acceptance_spacing_lower_bound"]
                   + inputs["scalar_acceptance_to_result_spacing_lower_bound"])
    matrix_span = inputs["matrix_layer1_cycles_lower_bound"]
    combined_span = max(matrix_span, scalar_span)
    useful = inputs["full_block_useful_macs_given"]
    capacity = inputs["fixed_matrix_macs"]
    return {
        "inputs": inputs,
        "mandatory_qk_scores": scores,
        "mandatory_qk_scalar_adds": adds,
        "mandatory_qk_scalar_scale_muls": muls,
        "mandatory_qk_scalar_operations": operations,
        "first_qk_scalar_accept_to_last_qk_scalar_result_span_lower_bound": scalar_span,
        "matrix_layer1_cycles_lower_bound": matrix_span,
        "combined_max_service_clock_cycles_lower_bound": combined_span,
        "fixed_4096_whole_block_capacity_denominator": capacity * combined_span,
        "scalar_layer2_utilization_upper_bound": Fraction(useful, capacity * scalar_span),
        "combined_architecture_utilization_upper_bound": Fraction(useful, capacity * combined_span),
    }


def verify_scalar_source(source_root):
    if source_root is None:
        raise ValueError("An explicit --source-root is required for fixture reads")
    pin_raw = (HERE / "SCALAR_SOURCE_PINS.json").read_bytes()
    if len(pin_raw) != SCALAR_PINS_BYTES or hashlib.sha256(pin_raw).hexdigest() != SCALAR_PINS_SHA256:
        raise ValueError("SCALAR_SOURCE_PINS byte identity mismatch")
    pins = json.loads(pin_raw)
    expected_source = {"bytes": BLOCKFLOAT_BYTES, "git_blob": BLOCKFLOAT_GIT_BLOB,
                       "mode": "100644", "sha256": BLOCKFLOAT_SHA256}
    if (pins.get("source_commit") != SOURCE_COMMIT or pins.get("source_tree") != SOURCE_TREE
            or pins.get("selected_qwen2block_sha256") != QWEN2BLOCK_SHA256
            or pins.get("identity_proof_sha256") != IDENTITY_PROOF_SHA256
            or pins.get("sources") != {BLOCKFLOAT_PATH: expected_source}):
        raise ValueError("SCALAR_SOURCE_PINS declared identities mismatch")
    raw = (Path(source_root) / BLOCKFLOAT_PATH).read_bytes()
    git_blob = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
    if (len(raw) != BLOCKFLOAT_BYTES or hashlib.sha256(raw).hexdigest() != BLOCKFLOAT_SHA256
            or git_blob != BLOCKFLOAT_GIT_BLOB):
        raise ValueError("BlockFloat source byte identity mismatch")
    lines = raw.decode("utf-8").splitlines()
    for anchor in SOURCE_ANCHORS:
        if anchor["path"] != BLOCKFLOAT_PATH:
            continue
        first, last = anchor["lines_inclusive"]
        window = "\n".join(line.strip() for line in lines[first - 1:last])
        for excerpt in anchor["excerpt"].splitlines():
            if excerpt not in window:
                raise ValueError("BlockFloat source anchor mismatch")
    return {
        "dedicated_pins_path": "SCALAR_SOURCE_PINS.json",
        "dedicated_pins_sha256": SCALAR_PINS_SHA256,
        "pins": pins,
        "unchanged_blockfloat_body_hash_and_anchors_verified": True,
        "selected_qwen2block_body_read_by_this_program": False,
        "identity_proof_file_read_by_this_program": False,
        "scope": "Current-main BlockFloat bytes are verified; selected Qwen2Block anchors were reviewed separately against its exact postimage hash. No elaboration or runtime closure is claimed.",
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
        "claim_kind": "conditional_necessary_qk_scalar_architecture_upper_bound_layer2",
        "layer1_artifact": "ARCHITECTURE_BOUND.json",
        "layer_combination": "MAX of necessary cycle lower bounds, never SUM",
        "cycle_domain": "Elapsed shared root-clock span inherited by Qwen2Block and its local Scalar, not ABI/software ticks or active-only/gated-MAC counters.",
        "not_measured_utilization": True,
        "not_predicted_runtime": True,
        "python_scheduler_ticks_used_as_hardware_cycles": False,
        "native_rtl_eda_or_ci_validation": False,
        "premises": [
            "Successful canonical M128 causal Qwen2 block, twelve query heads, selected packed QK16 score-consumer path.",
            "Given full-block useful work remains 6014828544 MACs and fixed physical Matrix capacity remains 4096 MACs.",
            "All actual key scores are consumed through the selected core's one local BlockScalarFloat on the inherited service clock.",
            "Only mandatory QK reduction Add and scaling Mul work is counted; no PV, softmax, SiLU, normalization, or other Scalar budget is assumed.",
        ],
        "proof": [
            "Causal score count P = 12 * 128 * 129 / 2 = 99072.",
            "Selected source initializes sum to positive zero and issues all sixteen lane Adds, then one Mul per score: N = 17 * P = 1684224.",
            "Earliest accepted edge e0 enters normal; e1 registers ALU output and enters done; e2 may consume result and returns to idle; e3 may accept the next request.",
            "Thus accepted requests are at least three service clocks apart, and final result consumption is at least two clocks after its acceptance.",
            "First mandatory acceptance to last mandatory result span is at least 3 * (N - 1) + 2 = 5052671 service clocks.",
            "The whole block contains that span: C >= max(2310144, 5052671) = 5052671. Arbitrary Matrix and other-resource overlap is allowed.",
            "U <= 6014828544 / (4096 * 5052671) = 1468464/5052671 exactly.",
        ],
        "limitations": [
            "The three-clock Scalar acceptance spacing is deliberately optimistic; Qwen control bubbles, caller gaps, stalls, and all other work can only strengthen this necessary bound.",
            "Failed requests may bypass normal, but they cannot establish a successful full-block completion and are excluded from this conditional proof.",
            "The strict Add/Mul path and explicit first zero-add are counted as implemented; this is not a mathematical reduction-tree minimum.",
            "A new score consumer, extra scalar instances, altered clocks or different scalar state machine requires a new proof.",
            "No longer-sequence, synthesized Fmax, runtime measurement, numerical pass, or native/RTL/EDA/CI completion is claimed.",
        ],
        "source_identity": verify_scalar_source(source_root),
        "reviewed_source_anchors": SOURCE_ANCHORS,
        "exact_bound": _json_exact(scalar_bound()),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(evidence(args.source_root), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
