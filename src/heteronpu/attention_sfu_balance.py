"""Measured-calibrated DSE and numerical vectors for the L5.5 Attention SFU.

This is an E0 planning model. It consumes the accepted 4-lane tile / 4-row
merge measurements and predicts bounded 4/8/16-lane, 4/8/16-row candidates.
It does not replace RTL E1, DC E4, or integrated E3.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math

import numpy as np


@dataclass(frozen=True)
class MeasuredBaseline:
    tile_lanes: int = 4
    tile_rows: int = 16
    tile_scores: int = 512
    reduction_ops: int = 496
    tile_nominal_cycles: int = 357
    tile_stress_cycles: int = 372
    tile_area: float = 185_940.027
    merge_rows: int = 4
    merge_nominal_cycles: int = 289
    merge_stress_cycles: int = 307
    merge_area: float = 156_217.152
    q1024_tasks: int = 12_672
    q1024_merge_rows: int = 43_008
    fixed_full_model_cycles: float = 3_032_083_527.2
    layers: int = 28
    tokens: int = 1024
    clock_hz: int = 1_000_000_000
    target_tps: float = 300.0
    review_floor_tps: float = 315.0
    preferred_floor_tps: float = 320.0

    def __post_init__(self) -> None:
        if min(self.tile_lanes, self.tile_rows, self.tile_scores, self.merge_rows) <= 0:
            raise ValueError("invalid measured baseline")


@dataclass(frozen=True)
class Candidate:
    tile_lanes: int
    merge_rows: int
    tile_nominal_cycles: int
    tile_stress_cycles: int
    merge_nominal_cycles: int
    merge_stress_cycles: int
    nominal_sfu_cycles: int
    stress_sfu_cycles: int
    nominal_tps: float
    stress_tps: float
    nominal_margin_over_315: float
    stress_margin_over_315: float
    stress_margin_over_320: float
    area_upper_bound: float
    hard_floor_pass: bool
    preferred_floor_pass: bool
    balanced: bool


def _doublings(value: int, base: int) -> int:
    if value < base or value % base:
        raise ValueError("candidate geometry must be a power-of-two multiple of baseline")
    ratio = value // base
    if ratio & (ratio - 1):
        raise ValueError("candidate geometry must be a power-of-two multiple")
    return int(math.log2(ratio))


def predict_candidate(
    tile_lanes: int,
    merge_rows: int,
    *,
    baseline: MeasuredBaseline = MeasuredBaseline(),
    conservative_tile_penalty_per_doubling: int = 8,
    conservative_merge_penalty_per_doubling: int = 16,
) -> Candidate:
    lane_doublings = _doublings(tile_lanes, baseline.tile_lanes)
    row_doublings = _doublings(merge_rows, baseline.merge_rows)
    exp_work = math.ceil(baseline.tile_scores / tile_lanes)
    reduce_work = math.ceil(baseline.reduction_ops / tile_lanes)
    baseline_exp = math.ceil(baseline.tile_scores / baseline.tile_lanes)
    baseline_reduce = math.ceil(baseline.reduction_ops / baseline.tile_lanes)
    nominal_fixed = baseline.tile_nominal_cycles - baseline_exp - baseline_reduce
    stress_fixed = baseline.tile_stress_cycles - baseline_exp - baseline_reduce
    if nominal_fixed < 0 or stress_fixed < 0:
        raise AssertionError("measured cycle decomposition")
    tile_nominal = exp_work + reduce_work + nominal_fixed + lane_doublings * conservative_tile_penalty_per_doubling
    tile_stress = exp_work + reduce_work + stress_fixed + lane_doublings * conservative_tile_penalty_per_doubling
    merge_nominal = baseline.merge_nominal_cycles + row_doublings * conservative_merge_penalty_per_doubling
    merge_stress = baseline.merge_stress_cycles + row_doublings * conservative_merge_penalty_per_doubling
    groups = math.ceil(baseline.q1024_merge_rows / merge_rows)
    nominal_sfu = baseline.q1024_tasks * tile_nominal + groups * merge_nominal
    stress_sfu = baseline.q1024_tasks * tile_stress + groups * merge_stress

    def tps(sfu_cycles: int) -> float:
        full_cycles = baseline.fixed_full_model_cycles + baseline.layers * sfu_cycles
        return baseline.tokens * baseline.clock_hz / full_cycles

    nominal_tps = tps(nominal_sfu)
    stress_tps = tps(stress_sfu)
    area_upper = baseline.tile_area * (tile_lanes / baseline.tile_lanes) + baseline.merge_area * (merge_rows / baseline.merge_rows)
    return Candidate(tile_lanes, merge_rows, tile_nominal, tile_stress, merge_nominal, merge_stress, nominal_sfu, stress_sfu, nominal_tps, stress_tps, nominal_tps / baseline.review_floor_tps - 1.0, stress_tps / baseline.review_floor_tps - 1.0, stress_tps / baseline.preferred_floor_tps - 1.0, area_upper, stress_tps >= baseline.review_floor_tps, stress_tps >= baseline.preferred_floor_tps, tile_lanes == merge_rows)


def candidate_table(baseline: MeasuredBaseline = MeasuredBaseline()) -> tuple[Candidate, ...]:
    candidates = [predict_candidate(lanes, rows, baseline=baseline) for lanes in (4, 8, 16) for rows in (4, 8, 16)]
    return tuple(sorted(candidates, key=lambda item: (-item.preferred_floor_pass, -item.stress_tps, item.area_upper_bound)))


def maximum_uniform_latency_inflation(candidate: Candidate, baseline: MeasuredBaseline = MeasuredBaseline()) -> float:
    groups = math.ceil(baseline.q1024_merge_rows / candidate.merge_rows)
    lo, hi = 1.0, 4.0
    for _ in range(80):
        mid = (lo + hi) / 2.0
        tile = math.ceil(candidate.tile_stress_cycles * mid)
        merge = math.ceil(candidate.merge_stress_cycles * mid)
        sfu = baseline.q1024_tasks * tile + groups * merge
        full = baseline.fixed_full_model_cycles + baseline.layers * sfu
        rate = baseline.tokens * baseline.clock_hz / full
        if rate >= baseline.review_floor_tps:
            lo = mid
        else:
            hi = mid
    return lo


def _merge_summary(a, b):
    if a is None:
        return b
    m = np.float32(max(float(a[0]), float(b[0])))
    alpha = np.float32(np.exp(np.float32(a[0] - m)))
    beta = np.float32(np.exp(np.float32(b[0] - m)))
    l = np.float32(np.float32(a[1] * alpha) + np.float32(b[1] * beta))
    o = (a[2] * alpha + b[2] * beta).astype(np.float32)
    return m, l, o


def _summary(scores: np.ndarray, values: np.ndarray):
    m = np.float32(np.max(scores))
    w = np.exp((scores - m).astype(np.float32)).astype(np.float32)
    l = np.sum(w, dtype=np.float32)
    o = np.sum(w[:, None] * values, axis=0, dtype=np.float32)
    return m, l, o


def numerical_vector_report(seed: int = 0x8A8) -> dict[str, object]:
    rng = np.random.default_rng(seed)
    patterns = []
    patterns.append(("random", rng.normal(0.0, 2.0, size=(16, 32)).astype(np.float32)))
    patterns.append(("identical", np.zeros((16, 32), dtype=np.float32)))
    dominant = np.full((16, 32), -20.0, dtype=np.float32); dominant[:, 31] = 20.0
    patterns.append(("dominant_last", dominant))
    patterns.append(("extreme_range", np.tile(np.linspace(-80.0, 80.0, 32, dtype=np.float32), (16, 1))))
    boundary = np.full((16, 32), -8.0, dtype=np.float32); boundary[:, 0] = 8.0; boundary[:, 15] = 7.999; boundary[:, 16] = 7.998; boundary[:, 31] = 7.997
    patterns.append(("block_boundary", boundary))
    max_output_error = 0.0; max_sum_error = 0.0; case_hash = hashlib.sha256(); rows_checked = 0
    for name, scores in patterns:
        values = rng.normal(0.0, 0.25, size=(16, 32, 128)).astype(np.float32)
        for row in range(16):
            dense = _summary(scores[row], values[row]); left = _summary(scores[row, :16], values[row, :16]); right = _summary(scores[row, 16:], values[row, 16:]); merged = _merge_summary(left, right)
            dense_out = dense[2] / dense[1]; merged_out = merged[2] / merged[1]
            max_output_error = max(max_output_error, float(np.max(np.abs(dense_out - merged_out))))
            dense_weights = np.exp(scores[row] - np.max(scores[row])).astype(np.float32); dense_weights /= np.sum(dense_weights, dtype=np.float32)
            max_sum_error = max(max_sum_error, abs(float(np.sum(dense_weights, dtype=np.float32)) - 1.0))
            case_hash.update(name.encode()); case_hash.update(scores[row].tobytes()); case_hash.update(values[row].tobytes()); case_hash.update(merged_out.tobytes()); rows_checked += 1
    row_summaries = []; scores = rng.normal(0.0, 1.0, size=(8, 64)).astype(np.float32); values = rng.normal(0.0, 0.1, size=(8, 64, 128)).astype(np.float32)
    for row in range(8):
        row_summaries.append(_merge_summary(_summary(scores[row, :32], values[row, :32]), _summary(scores[row, 32:], values[row, 32:])))
    parallel_hash = hashlib.sha256(b"".join(item[2].tobytes() for item in row_summaries)).hexdigest()
    if max_output_error > 2.0e-6 or max_sum_error > 2.0e-6:
        raise AssertionError((max_output_error, max_sum_error))
    return {"schema_version": 1, "status": "PASS", "evidence_class": "balanced_8x8_numerical_vector_E0_not_RTL_E1", "patterns": [name for name, _ in patterns], "rows_checked": rows_checked, "eight_row_merge_checked": 8, "max_output_error": max_output_error, "max_weight_sum_error": max_sum_error, "case_sha256": case_hash.hexdigest(), "parallel_merge_sha256": parallel_hash}


def balance_report() -> dict[str, object]:
    baseline = MeasuredBaseline(); table = candidate_table(baseline)
    balanced = next(item for item in table if item.tile_lanes == 8 and item.merge_rows == 8)
    measured = next(item for item in table if item.tile_lanes == 4 and item.merge_rows == 4)
    if abs(measured.nominal_tps - 315.48870639174635) > 1e-9 or abs(measured.stress_tps - 314.44809739590767) > 1e-9:
        raise AssertionError("measured calibration")
    if not balanced.preferred_floor_pass:
        raise AssertionError("8x8 candidate lacks preferred margin")
    payload = {"schema_version": 1, "status": "PASS_SANDBOX_BALANCED_8X8_PREFLIGHT", "evidence_class": "measured_calibrated_DSE_and_numerical_E0_not_RTL_E1_E4_or_E3", "baseline": asdict(baseline), "measured_4x4_reproduction": asdict(measured), "recommended_8x8": {**asdict(balanced), "maximum_uniform_component_latency_inflation_before_315": maximum_uniform_latency_inflation(balanced, baseline), "stress_margin_percent_over_315": 100.0 * balanced.stress_margin_over_315, "stress_margin_percent_over_320": 100.0 * balanced.stress_margin_over_320, "preferred_component_targets": {"tile16_stress_cycles_max_for_320_with_merge323": 336, "merge8_stress_cycles_max_for_320_with_tile254": 516, "stress_projection_tps_min": 320.0, "hard_projection_tps_min": 315.0}}, "candidate_table": [asdict(item) for item in table], "numerical_vectors": numerical_vector_report(), "decision": "Proceed with balanced 8-lane tile and 8-row merge. 4x8 and 8x4 clear 315 but do not clear the preferred 320-t/s engineering floor in the conservative model.", "remaining_local_gates": ["8-lane tile RTL E1 under nominal and random backpressure", "8-row merge RTL E1 under nominal and random backpressure", "CLN22UL 1GHz WNS>=0 unmapped=0", "measured stress projection >=320 preferred and >=315 hard", "integrated Matrix/SFU/iDMA/DDR E3"]}
    payload["sha256"] = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return payload
