"""Full-logit parity metrics for backend acceptance.

Top-k agreement is useful but can hide large errors in the rest of the
vocabulary.  This module records both ranking and full-vector metrics.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any
import hashlib
import numpy as np


@dataclass(frozen=True)
class LogitThresholds:
    topk: int = 10
    required_topk_overlap: int = 10
    relative_l2_max: float = 1.0e-2
    cosine_min: float = 0.9999


def compare_logits(actual: np.ndarray, reference: np.ndarray, thresholds: LogitThresholds | None = None) -> dict[str, Any]:
    t = thresholds or LogitThresholds()
    a = np.asarray(actual, dtype=np.float64).reshape(-1)
    r = np.asarray(reference, dtype=np.float64).reshape(-1)
    if a.shape != r.shape or a.size == 0:
        raise ValueError("shape mismatch or empty logits")
    finite_equal = bool(np.array_equal(np.isfinite(a), np.isfinite(r)))
    finite = np.isfinite(a) & np.isfinite(r)
    if not finite.any():
        raise ValueError("no finite logits")
    delta = a[finite] - r[finite]
    ref_norm = float(np.linalg.norm(r[finite]))
    actual_norm = float(np.linalg.norm(a[finite]))
    relative_l2 = float(np.linalg.norm(delta) / max(ref_norm, np.finfo(np.float64).tiny))
    cosine = float(np.dot(a[finite], r[finite]) / max(actual_norm * ref_norm, np.finfo(np.float64).tiny))
    k = min(t.topk, a.size)
    at = np.argpartition(a, -k)[-k:]
    rt = np.argpartition(r, -k)[-k:]
    overlap = int(len(set(map(int, at)) & set(map(int, rt))))
    metrics = {
        "count": int(a.size),
        "finite_mask_equal": finite_equal,
        "argmax_actual": int(np.nanargmax(a)),
        "argmax_reference": int(np.nanargmax(r)),
        "topk": k,
        "topk_overlap": overlap,
        "max_abs": float(np.max(np.abs(delta))),
        "mean_abs": float(np.mean(np.abs(delta))),
        "rmse": float(np.sqrt(np.mean(delta * delta))),
        "relative_l2": relative_l2,
        "cosine": cosine,
    }
    checks = {
        "finite_mask_equal": finite_equal,
        "argmax_equal": metrics["argmax_actual"] == metrics["argmax_reference"],
        "topk_overlap": overlap >= min(t.required_topk_overlap, k),
        "relative_l2": relative_l2 <= t.relative_l2_max,
        "cosine": cosine >= t.cosine_min,
    }
    return {
        "schema_version": 1,
        "status": "PASS_FULL_LOGITS_PARITY" if all(checks.values()) else "FAIL_FULL_LOGITS_PARITY",
        "thresholds": asdict(t),
        "metrics": metrics,
        "checks": checks,
    }


def _file_provenance(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    data = p.read_bytes()
    return {
        "path": str(p),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "dtype": "float32",
    }


def compare_files(actual_path: str | Path, reference_path: str | Path, thresholds: LogitThresholds | None = None) -> dict[str, Any]:
    actual = np.fromfile(actual_path, dtype=np.float32)
    reference = np.fromfile(reference_path, dtype=np.float32)
    report = compare_logits(actual, reference, thresholds)
    report["inputs"] = {
        "actual": _file_provenance(actual_path),
        "reference": _file_provenance(reference_path),
    }
    return report
