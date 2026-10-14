"""Explicit pinned-runtime smoke; no cold-suite skips or producer execution.

Run using work/runtime_recovery/python.sh -m
candidates.qwen35_35b_postnorm.pinned_reference_smoke [--actual]. The optional
actual probe reads frozen previous O outputs and original hidden bytes only.
It never runs a new owner chain, downloads weights, or admits a tolerance.
"""
from __future__ import annotations

import argparse
import ast
from contextlib import ExitStack
import json
import os
from pathlib import Path
import struct
from unittest import mock

from . import reference as r

ACTUAL_PINS = {
    16: dict(summary_sha256="2c3ff31e24449ca20c255599d466f433249f7c1f09dd4cd631c510c1c7f3ccb3",
             hidden_sha256="43c2d85ac87a85a84883b88d8e03fb27d8afdab702e96f7af0e5951f77d0a04c",
             o_sha256="8ab405b2413155809f3ae6b64830eca183eaab6f1a309f6ec3f8cc323c20fa0b"),
    128: dict(summary_sha256="8f9aaad4c06fce4176d0976c01579e814695d44814eb3d7de55c37a506f6da69",
              hidden_sha256="26401a9f20dbafc14cfd85db960b3034a47f88ae871b1a575730c936e0ea9797",
              o_sha256="38b32aa2bef094242a6fc12ae6da3a15a61d9234ffde2aa5f3f41b9eca1c1cb4"),
}
POSTNORM_MANIFEST_SHA = "9fe42b27599c7e83524b899638f595b8bac9e5c6c4eaf2750a18c9a521712ba0"


def _words(values, count):
    return b"".join(struct.pack("<H", values[i % len(values)]) for i in range(count))


def synthetic_case(name, tokens):
    if name == "zero":
        return bytes(tokens * 4096), bytes(tokens * 4096), bytes(4096)
    hidden = _words([0, 0x8000, 0x3f80, 0x3f81, 0xbf80, 0xbf81, 1, 0x8001, 0x3f80, 0x4000], tokens * 2048)
    actual_o = _words([0x8000, 0x8000, 0x3b80, 0x3b80, 0xbb80, 0xbb80, 1, 0x8001, 0xbf80, 0xc000], tokens * 2048)
    weight = _words([0, 0x8000, 0x3e80, 0xbe80, 0xbf80, 0x3f80, 1, 0x8001], 2048)
    return hidden, actual_o, weight


def retained_actual_case(tokens, payload, manifest_sha256):
    """Verify old actual O's publication and the same original hidden input."""
    from . import payload as postnorm_payload
    r.require(type(tokens) is int and tokens in ACTUAL_PINS, "retained actual M16/M128 only")
    pin = ACTUAL_PINS[tokens]
    directory = r.ROOT / f"work/output_actual_m{tokens}"
    summary_raw = (directory / "summary.json").read_bytes()
    r.require(r.sha(summary_raw) == pin["summary_sha256"], "retained O producer summary drift")
    summary = json.loads(summary_raw)
    r.require(summary["tokens"] == tokens and summary["output_projection_requested"] is True and
              summary["sources_unchanged"] is True and
              summary["source_sha256"] == summary["source_sha256_after"] and
              bool(summary["source_sha256"]), "retained O producer/source freeze")
    r.require(summary["input_identity"]["hidden_sha256"] == pin["hidden_sha256"], "original hidden identity drift")
    execution = summary["execution"]
    r.require(execution["status"] == "PASS_TYPED_OUTPUT_PREFIX_EXECUTION_ONLY" and
              execution["tokens"] == tokens, "retained actual O execution scope")
    observations = [item for item in summary["observations"] if item["stage"] == "output_projection"]
    stages = [item for item in execution["stages"] if item["stage"] == "output_projection"]
    terminals = [item for item in execution["terminals"] if item["stage"] == "output_projection"]
    r.require(len(observations) == len(stages) == len(terminals) == 1 and terminals[0]["status"] is None,
              "one complete successful actual O publication required")
    observed, report = observations[0], stages[0]["report"]
    r.require(observed["owner"]["complete"] is True and observed["owner"]["output_published"] is True and
              report["complete"] is True and
              observed["owner"]["output_sha256"] == report["output_sha256"] == pin["o_sha256"],
              "retained actual O owner publication agreement")
    path = directory / "output_projection.actual.bf16le"
    record = observed["output"]
    r.require(Path(record["path"]).resolve() == path.resolve() and record["bytes"] == tokens * 4096 and
              record["sha256"] == pin["o_sha256"], "actual O file binding")
    actual_o = path.read_bytes()
    hidden_path = r.ROOT / f"work/recovery_rms_actual_v2/actual_embedding_rms_m{tokens}.input.bin"
    hidden = hidden_path.read_bytes()
    r.require(r.sha(actual_o) == pin["o_sha256"] and r.sha(hidden) == pin["hidden_sha256"],
              "actual O/original hidden bytes drift")
    _, values = postnorm_payload.load(payload, manifest_sha256)
    weight = values["layers.0.post_attention_layernorm.weight"]
    r.validate_raw(hidden, actual_o, weight, tokens)
    evidence = dict(kind="retained_actual_O_and_same_original_hidden", tokens=tokens,
                    producer_summary=str(directory / "summary.json"), producer_summary_sha256=pin["summary_sha256"],
                    hidden_path=str(hidden_path), hidden_sha256=pin["hidden_sha256"],
                    o_path=str(path), o_sha256=pin["o_sha256"],
                    postnorm_manifest_sha256=manifest_sha256, weight_sha256=r.sha(weight),
                    source_before=summary["source_sha256"], source_after=summary["source_sha256_after"],
                    new_owner_chain_executed=False, full_checkpoint_sha256_verified=False,
                    actual_producer_bytes_replaced=False)
    return hidden, actual_o, weight, evidence


def direct_original(hidden_raw, o_raw, weight_raw, tokens):
    """Unobserved original AST execution tests observer/wrapper transparency."""
    import torch
    nodes, _ = r._source_definition()
    cls, _ = r.rms.source_class()
    with torch.device("meta"):
        norm = cls(r.WIDTH, eps=r.EPS)
    norm.load_state_dict({"weight": torch.frombuffer(bytearray(weight_raw), dtype=torch.bfloat16)}, assign=True)
    model = torch.nn.Module()
    model.post_attention_layernorm = norm
    model.eval()
    namespace = dict(self=model,
        residual=torch.frombuffer(bytearray(hidden_raw), dtype=torch.bfloat16).reshape(1, tokens, r.WIDTH),
        hidden_states=torch.frombuffer(bytearray(o_raw), dtype=torch.bfloat16).reshape(1, tokens, r.WIDTH))
    results = []
    with torch.inference_mode(), torch.autocast("cpu", enabled=False):
        for node in nodes:
            exec(compile(ast.Module(body=[node], type_ignores=[]), str(r.ROOT / r.SOURCE), "exec"), namespace)
            results.append(namespace["hidden_states"].view(torch.uint16).numpy().astype("<u2", copy=False).tobytes())
    return tuple(results)


def run_case(output, name, tokens, hidden, actual_o, weight, evidence):
    import torch
    with ExitStack() as stack:
        for setter in ("set_num_threads", "set_num_interop_threads", "use_deterministic_algorithms",
                       "set_float32_matmul_precision", "set_flush_denormal"):
            stack.enter_context(mock.patch.object(torch, setter, side_effect=AssertionError("reference called " + setter)))
        result = r.component(hidden, actual_o, weight, tokens)
    direct_residual, direct_postnorm = direct_original(hidden, actual_o, weight, tokens)
    r.require(result["residual"] == direct_residual and result["output"] == direct_postnorm,
              "observer/wrapper changed original output")
    # This is the same official RMS on the observed BF16 residual, not a second
    # independent arithmetic oracle. Compare all observations as an ABI smoke.
    original_rms = r.rms.component(result["residual"], weight, tokens)
    r.require(result["output"] == original_rms["output"] and result["rms_operations"] == original_rms["operations"] and
              set(result["trace"]) == set(original_rms["trace"]) and all(
                  result["trace"][key].tobytes() == original_rms["trace"][key].tobytes() for key in result["trace"]),
              "existing original RMS observation compatibility")
    r.require(result["operations"] == [op for op, _ in r.SEQUENCE] and
              result["passed"] is None and result["thresholds"] is None, "dispatch/claim boundary")
    if name == "zero":
        r.require(result["residual"] == result["output"] == bytes(tokens * 4096), "zero witness")
    elif name == "ties":
        expected = _words([0, 0x8000, 0x3f80, 0x3f82, 0xbf80, 0xbf82, 2, 0x8002, 0, 0], tokens * 2048)
        r.require(result["residual"] == expected, "BF16 residual RNE/signed-zero/subnormal/cancellation witness")
    directory = output / f"{name}_m{tokens}"
    directory.mkdir()
    records = {}
    for key in ("residual", "postnorm"):
        path = directory / (key + ".reference.bf16le")
        path.write_bytes(result[key])
        records[key] = dict(path=str(path), bytes=len(result[key]), sha256=r.sha(path.read_bytes()))
    for key, raw in result["trace_raw"].items():
        path = directory / ("rms." + key + ".fp32le")
        path.write_bytes(raw)
        records[key] = dict(path=str(path), bytes=len(raw), sha256=r.sha(path.read_bytes()),
                            dtype=str(result["trace"][key].dtype), shape=list(result["trace"][key].shape),
                            provenance=result["trace_provenance"][key])
    identity = {key: value for key, value in result.items() if key not in
                ("residual", "output", "postnorm", "trace", "trace_raw")}
    identity.update(input_evidence=evidence, records=records,
                    unobserved_original_AST_bytes_equal=True, existing_original_RMS_trace_bytes_equal=True,
                    independent_arithmetic_oracle=False)
    (directory / "identity.json").write_text(json.dumps(identity, indent=2, sort_keys=True) + "\n")
    summary = dict(case=name, tokens=tokens, residual_sha256=result["residual_sha256"],
                   postnorm_sha256=result["postnorm_sha256"], original_dispatches=len(result["operations"]),
                   unobserved_original_AST_bytes_equal=True, existing_original_RMS_trace_bytes_equal=True,
                   actual_payload=name == "actual", passed=None, thresholds=None)
    print(json.dumps(summary), flush=True)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--actual", action="store_true", help="also require retained actual M16/M128; never skip missing artifacts")
    parser.add_argument("--payload", type=Path, default=r.ROOT / "work/qwen35_35b_postnorm_payload")
    parser.add_argument("--manifest-sha256", default=POSTNORM_MANIFEST_SHA)
    parser.add_argument("--output", type=Path, default=r.ROOT / "work/postnorm_pinned_smoke")
    args = parser.parse_args(argv)
    output = args.output.resolve()
    r.require(output.is_relative_to(r.ROOT / "work") and not output.exists(), "fresh ignored work output required")
    os.environ["HETERO_35B_RUNTIME_PROFILE"] = "recovery_20261013"
    import torch
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.set_float32_matmul_precision("highest")
    torch.set_flush_denormal(False)
    r.runtime_identity()  # Missing runtime or wrong binaries fails, never skips.
    output.mkdir(parents=True)
    results = []
    for name, tokens in (("zero", 1), ("ties", 1), ("ties", 16), ("ties", 128)):
        hidden, actual_o, weight = synthetic_case(name, tokens)
        results.append(run_case(output, name, tokens, hidden, actual_o, weight,
                                dict(kind="synthetic_exact_BF16_words", actual_payload=False)))
    if args.actual:
        for tokens in (16, 128):
            hidden, actual_o, weight, evidence = retained_actual_case(tokens, args.payload, args.manifest_sha256)
            results.append(run_case(output, "actual", tokens, hidden, actual_o, weight, evidence))
            # Reopen every external input binding after the component probe.
            repeated = retained_actual_case(tokens, args.payload, args.manifest_sha256)
            r.require(repeated[:3] == (hidden, actual_o, weight) and repeated[3] == evidence,
                      "retained input changed during probe")
    summary = dict(status="PINNED_ORIGINAL_RESIDUAL_POSTNORM_COMPONENT_SMOKE_COMPLETE",
                   cases=results, actual_requested=args.actual, no_new_owner_chain=True,
                   no_downloads=True, no_reference_producer_fill=True, full_native_forward=False,
                   independent_arithmetic_oracle=False, passed=None, thresholds=None)
    (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(str(output / "summary.json"), flush=True)


if __name__ == "__main__":
    main()
