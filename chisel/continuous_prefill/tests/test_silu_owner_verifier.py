"""Fail-closed parser tests. Synthetic logs exercise the parser, not RTL."""
from __future__ import annotations
import importlib.util
import sys
from pathlib import Path
import pytest

SPEC = importlib.util.spec_from_file_location(
    "silu_verifier", Path(__file__).resolve().parents[1] / "scripts/verify_silu_owner_gate.py")
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def valid_log() -> str:
    lines = ["Tests: succeeded 4, failed 0, canceled 0, ignored 0, pending 0", "All tests passed.",
             "SILU_OWNER_SUITE_PASS mode=baseline numeric_cases=13 fault_cases=0",
             "SILU_OWNER_SUITE_PASS mode=overlap numeric_cases=17 fault_cases=6",
             "SILU_OWNER_REJECT_PASS cases=7 memory_requests=0",
             "SILU_VECTOR_EXACT_PASS checked_fp32=192 lanes=16"]
    cases = [(mode, (16, 32, 64, 256)[seed % 4], seed, "none")
             for mode in ("baseline", "overlap") for seed in range(1, 13)]
    cases += [(mode, 1024, 101, "none") for mode in ("baseline", "overlap")]
    cases += [("overlap", 32, seed, "none") for seed in range(220, 224)]
    cases += [("overlap", 64, seed, fault) for seed, fault in
              ((201, "numerical-late-store"), (202, "numerical-stalled-store"),
               (210, "read-gate"), (211, "read-up"), (212, "last-store"), (213, "tag"))]
    for mode, n, seed, fault in cases:
        written = n * 4 if fault == "none" else 64
        late = "true" if fault.startswith("numerical") else "false"
        lines += [f"SILU_OWNER_ACK_OBSERVED mode={mode} fault={fault} acknowledged_bytes={written} reported_bytes={written} late_ack={late}",
                  f"SILU_OWNER_CASE mode={mode} elements={n} seed={seed} fault={fault} cycles=100 checked_fp32={n} read_beats={n // 8} write_ack_bytes={written}"]
    return "\n".join(lines) + "\n"


def verify_at(tmp_path: Path, text: str, source: str = "SOURCE_IMMUTABILITY_PASS") -> dict:
    (tmp_path / "tests.log").write_text(text)
    (tmp_path / "source_verify.log").write_text(source)
    return MOD.verify(tmp_path)


def test_valid_scope_and_complete_case_set(tmp_path):
    r = verify_at(tmp_path, valid_log())
    assert r["numeric_owner_cases"] == 30 and r["fault_cases"] == 6
    assert len(r["comparison"]) == 13
    assert not r["scope"]["pinned_idma_in_this_test"]
    assert not r["scope"]["host_real16_two_layer"]
    assert not r["scope"]["physical_timing_signoff"]


@pytest.mark.parametrize("old,new", [
    ("All tests passed.", "test interrupted"),
    ("succeeded 4", "succeeded 3"),
    ("cases=7 memory_requests=0", "cases=6 memory_requests=0"),
    ("numeric_cases=17", "numeric_cases=16"),
    ("seed=101", "seed=102"),
    ("cycles=100", "cycles=0"),
    ("checked_fp32=32", "checked_fp32=16"),
    ("read_beats=4", "read_beats=3"),
    ("write_ack_bytes=128", "write_ack_bytes=64"),
    ("reported_bytes=128", "reported_bytes=0"),
    ("late_ack=true", "late_ack=false"),
    ("fault=numerical-late-store", "fault=untested-error"),
])
def test_reject_changed_case_or_counter(tmp_path, old, new):
    with pytest.raises(ValueError):
        verify_at(tmp_path, valid_log().replace(old, new, 1))


@pytest.mark.parametrize("prefix", ["SILU_OWNER_CASE ", "SILU_OWNER_ACK_OBSERVED ", "SILU_OWNER_SUITE_PASS "])
def test_reject_missing_and_duplicate_records(tmp_path, prefix):
    text = valid_log()
    line = next(x for x in text.splitlines(True) if x.startswith(prefix))
    with pytest.raises(ValueError):
        verify_at(tmp_path, text.replace(line, "", 1))
    with pytest.raises(ValueError):
        verify_at(tmp_path, text + line)


def test_reject_failure_even_with_pass_markers(tmp_path):
    with pytest.raises(ValueError):
        verify_at(tmp_path, valid_log() + "%Error numerical mismatch\n")


def test_reject_unverified_source(tmp_path):
    with pytest.raises(ValueError):
        verify_at(tmp_path, valid_log(), source="SOURCE_CHANGED")
