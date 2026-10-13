"""Bounded component comparison. Run under the isolated python.sh wrapper."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import resource
import signal
import sys
import time

from . import reference as r


def budget():
    r.require("torch" not in sys.modules, "configure budget before Torch import")
    r.require(os.environ.get("ATEN_CPU_CAPABILITY") == "default", "use pinned wrapper")
    for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        r.require(os.environ.get(key) == "1", "single-thread environment required: " + key)
    resource.setrlimit(resource.RLIMIT_CPU, (55, 55))
    def expired(signum, frame):
        raise TimeoutError("35B RMS diagnostic exceeded 55-second wall budget")
    signal.signal(signal.SIGALRM, expired)
    signal.alarm(55)


def synthetic_cases():
    import numpy as np
    from .formula import bf16
    rng = np.random.default_rng(352048)
    weight = bf16(rng.uniform(-.75, .75, r.WIDTH).astype("<f4"))
    for m in (16, 128):
        x = rng.normal(size=(m, r.WIDTH)).astype("<f4")
        yield "synthetic_random_m" + str(m), bf16(x), weight, m, dict(kind="synthetic", seed=352048)
    x = np.zeros((16, r.WIDTH), dtype="<f4")
    x[0, 1::2] = -0.0
    x[1] = 1
    x[2] = -1
    x[3] = np.float32(.001)
    x[4, 0] = 1
    x[5, 1::2], x[5, ::2] = np.float32(2.0 ** -133), np.float32(-2.0 ** -133)
    x[6] = np.float32(2.0 ** -70)
    x[7] = np.float32(2.0 ** 55)
    x[8, ::2], x[8, 1::2] = np.float32(2.0 ** 14), np.float32(2.0 ** -14)
    x[9] = np.ldexp(np.ones(r.WIDTH, dtype="<f4"), np.arange(r.WIDTH) % 41 - 20)
    x[10] = np.linspace(-4, 4, r.WIDTH, dtype="<f4")
    x[11] = rng.uniform(-.01, .01, r.WIDTH).astype("<f4")
    x[12] = np.float32(2.0 ** -63)
    x[13, 0], x[13, -1] = 3, -3
    x[14] = np.float32(1.0078125)
    x[15] = rng.uniform(-32, 32, r.WIDTH).astype("<f4")
    ew = np.resize(np.array([-1, -.99609375, -1.0078125, 0, -0.0, 1, 2.0 ** -70, .5], dtype="<f4"), r.WIDTH)
    yield "synthetic_edges_m16", bf16(x), bf16(ew), 16, dict(kind="synthetic", rows=[
        "signed_zero", "unit", "negative_unit", "epsilon_scale", "one_hot", "BF16_min_subnormal",
        "FP32_square_underflow", "large_safe_square_sum", "mixed_powers", "wide_exponent",
        "ramp", "small_random", "FP32_min_normal_square", "boundary_hot", "BF16_neighbor", "large_random"],
        weights="-1 cancellation, adjacent BF16 gamma, signed zero, small and positive")
    yield "synthetic_edges_m128", bf16(np.tile(x, (8, 1))), bf16(ew), 128, dict(kind="synthetic", rows="eight repeats of edge M16")


def fp32_stats(actual, expected):
    import numpy as np
    r.require(actual.shape == expected.shape, "trace shape drift")
    a, b = np.asarray(actual, "<f4"), np.asarray(expected, "<f4")
    r.require(np.isfinite(a).all() and np.isfinite(b).all(), "nonfinite trace comparison")
    mismatch = a.view("<u4") != b.view("<u4")
    delta = np.abs(a.astype(np.float64) - b.astype(np.float64))
    return dict(elements=int(a.size), bit_mismatches=int(np.count_nonzero(mismatch)),
                max_abs=float(delta.max()), mean_abs=float(delta.mean()),
                first_flat_mismatch=int(np.flatnonzero(mismatch)[0]) if mismatch.any() else None,
                actual_sha256=r.sha(a.tobytes()), expected_sha256=r.sha(b.tobytes()))


def compare_case(name, hidden, weight, tokens, provenance):
    import numpy as np
    from candidates.qwen35_gdn_prefill.prefill_bf16_compare import compare_finite_bf16
    from heteronpu.matrix_norm_rope_candidate import MAX_ABS, MEAN_ABS
    from .formula import bf16, formula
    r.require((MAX_ABS, MEAN_ABS) == (.03125, .005), "original per-node thresholds changed")
    official = r.component(hidden, weight, tokens)
    candidate = formula(hidden, weight, tokens)
    native, model = official["trace"], candidate["trace"]
    stage_names = ("input_fp32", "squares", "sum", "mean", "mean_eps", "inverse", "scaled", "weight_fp32", "gamma", "weighted")
    stages = {stage: fp32_stats(model[stage], native["sum_auxiliary" if stage == "sum" else stage]) for stage in stage_names}
    # Condition each downstream check on actual upstream native values. This
    # separates reduction drift from rsqrt implementation and materialization.
    direct_inverse = np.divide(np.float32(1), np.sqrt(native["mean_eps"], dtype=np.float32), dtype=np.float32)
    isolated = {
        "native_mean_vs_auxiliary_sum_times_reciprocal": fp32_stats(np.multiply(native["sum_auxiliary"], np.float32(1 / r.WIDTH), dtype=np.float32), native["mean"]),
        "sqrt_div_vs_native_rsqrt_same_variance": fp32_stats(direct_inverse, native["inverse"]),
        "scaled_from_native_input_inverse": fp32_stats(np.multiply(native["input_fp32"], native["inverse"], dtype=np.float32), native["scaled"]),
        "weighted_from_native_scaled_gamma": fp32_stats(np.multiply(native["scaled"], native["gamma"], dtype=np.float32), native["weighted"]),
        "materialize_native_weighted": compare_finite_bf16(bf16(native["weighted"]), official["output"]),
    }
    output = compare_finite_bf16(candidate["output"], official["output"])
    output.update(thresholds=dict(max_abs=MAX_ABS, mean_abs=MEAN_ABS),
                  passed=output["max_abs"] <= MAX_ABS and output["mean_abs"] <= MEAN_ABS,
                  gate="ORIGINAL_NATIVE_PER_NODE")
    legacy = formula(hidden, weight, tokens, reduction="legacy_ascending")
    first = next((stage for stage in stage_names if stages[stage]["bit_mismatches"]), None)
    return dict(name=name, shape=[1, tokens, r.WIDTH], provenance=provenance,
        input_sha256=r.sha(hidden), weight_sha256=r.sha(weight),
        official_component=official["source"], actual_operations=official["operations"],
        stages=stages, isolated_stages=isolated, output=output, first_fp32_divergence=first,
        exact_output=output["bit_mismatches"] == 0,
        legacy_control=dict(sum=fp32_stats(legacy["trace"]["sum"], native["sum_auxiliary"]),
                            output=compare_finite_bf16(legacy["output"], official["output"])))


def imported_repository_sources():
    """Hash actual imported local Python dependencies, excluding runtime files.

    This does not glob sibling work in progress such as the independent owner.
    It is an import observation, not complete native dependency source closure.
    """
    files = set()
    for module in tuple(sys.modules.values()):
        name = getattr(module, "__file__", None)
        if isinstance(name, str) and Path(name).is_absolute():
            path = Path(name).resolve()
            if path.suffix == ".py" and path.is_relative_to(r.ROOT) and not path.is_relative_to(r.ROOT / "work"):
                files.add(path)
    return {str(path.relative_to(r.ROOT)): r.file_sha(path) for path in sorted(files)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--payload", type=Path)
    parser.add_argument("--manifest-sha256")
    args = parser.parse_args(argv)
    r.require(bool(args.payload) == bool(args.manifest_sha256), "payload and retained digest must be supplied together")
    r.require(not args.output.exists(), "fresh output directory required")
    budget()
    started, cpu = time.monotonic(), time.process_time()
    import torch
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    runtime = r.runtime_identity()
    cases = list(synthetic_cases())
    if args.payload:
        for m in (16, 128):
            ids = list(range(m))
            hidden, weight, provenance = r.payload_case(args.payload, args.manifest_sha256, ids)
            cases.append(("actual_embedding_rows_0_" + str(m - 1), hidden, weight, m, provenance))
    results = [compare_case(*case) for case in cases]
    report = dict(status="PASS_COMPONENT_COMPARISON" if all(v["output"]["passed"] for v in results) else "FAIL_COMPONENT_COMPARISON",
        runtime=runtime, cases=results, formula="8 lanes x 4 residues x 4 blocks x 16 ascending terms; residue then lane reduction",
        elapsed_seconds=time.monotonic() - started, cpu_seconds=time.process_time() - cpu,
        implementation_sha256={name: r.file_sha(Path(__file__).parent / name)
                               for name in ("reference.py", "formula.py", "diagnose.py")},
        imported_repository_sources_sha256=imported_repository_sources(),
        limits=dict(cpu_seconds=55, wall_seconds=55),
        claim_boundary=dict(official_component_executed=True, full_native_forward=False,
            model_weights_downloaded_by_diagnostic=False, full_checkpoint_loaded=False,
            chisel_executed=False, rtl_executed=False, hardware_storage_or_latency_proven=False,
            scalar_exception_policy_executed=False, actual_payload_executed=bool(args.payload)))
    args.output.mkdir(parents=True)
    (args.output / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    signal.alarm(0)
    print(json.dumps(dict(status=report["status"], cases=[dict(name=c["name"], exact_output=c["exact_output"],
        first_fp32_divergence=c["first_fp32_divergence"], output_bit_mismatches=c["output"]["bit_mismatches"],
        max_abs=c["output"]["max_abs"], mean_abs=c["output"]["mean_abs"]) for c in results],
        cpu_seconds=report["cpu_seconds"], elapsed_seconds=report["elapsed_seconds"], report=str(args.output / "report.json")), indent=2))
    if report["status"].startswith("FAIL"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
