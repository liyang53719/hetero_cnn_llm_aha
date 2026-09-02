"""Full-logit parity metrics for backend acceptance.

Top-k agreement alone can hide large errors in the rest of the vocabulary.
This module therefore records deterministic ranking, full-vector error metrics,
non-finite classifications, an expected vocabulary size and raw-file
provenance.  It intentionally does not infer hardware execution from numerical
agreement; execution provenance is audited separately.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path
from typing import Any

import numpy as np

_FLOAT32_BYTES = np.dtype("<f4").itemsize


@dataclass(frozen=True)
class LogitThresholds:
    topk: int = 10
    required_topk_overlap: int = 10
    relative_l2_max: float = 1.0e-2
    cosine_min: float = 0.9999
    expected_count: int | None = None
    require_all_finite: bool = True

    def __post_init__(self) -> None:
        if self.topk <= 0:
            raise ValueError("topk must be positive")
        if self.required_topk_overlap < 0:
            raise ValueError("required_topk_overlap must be non-negative")
        if self.required_topk_overlap > self.topk:
            raise ValueError("required_topk_overlap cannot exceed topk")
        if self.relative_l2_max < 0:
            raise ValueError("relative_l2_max must be non-negative")
        if not -1.0 <= self.cosine_min <= 1.0:
            raise ValueError("cosine_min must be in [-1, 1]")
        if self.expected_count is not None and self.expected_count <= 0:
            raise ValueError("expected_count must be positive when provided")


def _ranking_values(values: np.ndarray) -> np.ndarray:
    """Return values suitable for deterministic ranking.

    NaN is ranked below every numeric value.  Positive/negative infinity keep
    their mathematical ordering.  Acceptance still fails non-finite vectors by
    default; this conversion only keeps diagnostic ranking deterministic.
    """

    return np.nan_to_num(values, nan=-np.inf, posinf=np.inf, neginf=-np.inf)


def _stable_topk(values: np.ndarray, k: int) -> np.ndarray:
    """Highest ``k`` indices, with the lower index winning exact ties."""

    ranked = _ranking_values(values)
    indices = np.arange(ranked.size, dtype=np.int64)
    order = np.lexsort((indices, -ranked))
    return order[:k]


def _stable_argmax(values: np.ndarray) -> int:
    return int(_stable_topk(values, 1)[0])


def _cosine(actual: np.ndarray, reference: np.ndarray, delta_norm: float) -> float:
    actual_norm = float(np.linalg.norm(actual))
    reference_norm = float(np.linalg.norm(reference))
    if actual_norm == 0.0 and reference_norm == 0.0:
        return 1.0 if delta_norm == 0.0 else 0.0
    if actual_norm == 0.0 or reference_norm == 0.0:
        return 0.0
    value = float(np.dot(actual, reference) / (actual_norm * reference_norm))
    # Roundoff can push an otherwise valid cosine a few ulps outside [-1, 1].
    return float(np.clip(value, -1.0, 1.0))


def compare_logits(
    actual: np.ndarray,
    reference: np.ndarray,
    thresholds: LogitThresholds | None = None,
) -> dict[str, Any]:
    t = thresholds or LogitThresholds()
    a = np.asarray(actual, dtype=np.float64).reshape(-1)
    r = np.asarray(reference, dtype=np.float64).reshape(-1)
    if a.shape != r.shape or a.size == 0:
        raise ValueError("shape mismatch or empty logits")

    finite_a = np.isfinite(a)
    finite_r = np.isfinite(r)
    finite_mask_equal = bool(np.array_equal(finite_a, finite_r))
    all_finite = bool(finite_a.all() and finite_r.all())
    finite_both = finite_a & finite_r

    if finite_both.any():
        a_finite = a[finite_both]
        r_finite = r[finite_both]
        delta = a_finite - r_finite
        delta_norm = float(np.linalg.norm(delta))
        reference_norm = float(np.linalg.norm(r_finite))
        if reference_norm == 0.0:
            relative_l2 = 0.0 if delta_norm == 0.0 else None
        else:
            relative_l2 = float(delta_norm / reference_norm)
        cosine = _cosine(a_finite, r_finite, delta_norm)
        max_abs = float(np.max(np.abs(delta)))
        mean_abs = float(np.mean(np.abs(delta)))
        rmse = float(np.sqrt(np.mean(delta * delta)))
    else:
        # Keep malformed vectors reportable instead of raising after provenance
        # has already been gathered.  Strict finite acceptance will fail them.
        relative_l2 = None
        cosine = None
        max_abs = None
        mean_abs = None
        rmse = None

    k = min(t.topk, a.size)
    actual_topk = _stable_topk(a, k)
    reference_topk = _stable_topk(r, k)
    overlap = int(len(set(map(int, actual_topk)) & set(map(int, reference_topk))))
    argmax_actual = _stable_argmax(a)
    argmax_reference = _stable_argmax(r)
    count_matches = t.expected_count is None or a.size == t.expected_count

    metrics = {
        "count": int(a.size),
        "expected_count": t.expected_count,
        "finite_mask_equal": finite_mask_equal,
        "all_finite": all_finite,
        "nonfinite_actual": int((~finite_a).sum()),
        "nonfinite_reference": int((~finite_r).sum()),
        "nan_actual": int(np.isnan(a).sum()),
        "nan_reference": int(np.isnan(r).sum()),
        "positive_inf_actual": int(np.isposinf(a).sum()),
        "positive_inf_reference": int(np.isposinf(r).sum()),
        "negative_inf_actual": int(np.isneginf(a).sum()),
        "negative_inf_reference": int(np.isneginf(r).sum()),
        "argmax_actual": argmax_actual,
        "argmax_reference": argmax_reference,
        "topk": k,
        "topk_actual_indices": [int(x) for x in actual_topk],
        "topk_reference_indices": [int(x) for x in reference_topk],
        "topk_overlap": overlap,
        "max_abs": max_abs,
        "mean_abs": mean_abs,
        "rmse": rmse,
        "relative_l2": relative_l2,
        "cosine": cosine,
    }
    checks = {
        "count": bool(count_matches),
        "finite_mask_equal": finite_mask_equal,
        "all_finite": all_finite if t.require_all_finite else True,
        "argmax_equal": argmax_actual == argmax_reference,
        "topk_overlap": overlap >= min(t.required_topk_overlap, k),
        "relative_l2": relative_l2 is not None and relative_l2 <= t.relative_l2_max,
        "cosine": cosine is not None and cosine >= t.cosine_min,
    }
    return {
        "schema_version": 2,
        "status": "PASS_FULL_LOGITS_PARITY" if all(checks.values()) else "FAIL_FULL_LOGITS_PARITY",
        "thresholds": asdict(t),
        "metrics": metrics,
        "checks": checks,
        "ranking_tie_break": "lower_index_first",
    }


def _file_provenance(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    size = p.stat().st_size
    if size % _FLOAT32_BYTES:
        raise ValueError(f"{p} byte count {size} is not a multiple of float32")
    with p.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {
        "path": str(p),
        "bytes": size,
        "elements": size // _FLOAT32_BYTES,
        "sha256": digest,
        "dtype": "float32_le",
    }


def compare_files(
    actual_path: str | Path,
    reference_path: str | Path,
    thresholds: LogitThresholds | None = None,
) -> dict[str, Any]:
    actual_info = _file_provenance(actual_path)
    reference_info = _file_provenance(reference_path)
    actual = np.fromfile(actual_path, dtype="<f4")
    reference = np.fromfile(reference_path, dtype="<f4")
    report = compare_logits(actual, reference, thresholds)
    report["inputs"] = {"actual": actual_info, "reference": reference_info}
    return report
