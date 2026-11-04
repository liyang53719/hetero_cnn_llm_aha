"""Source-only P1 FIRST policy and one-shot derived controller binding.

This module performs JSON/file admission, never native execution. It does not
replace structural build, reference, cleanup, resource, or numerical verifiers.
The root controller pin must come from the already admitted owning invocation,
not from an untrusted derived document. The clock_id identifies the same boot /
monotonic epoch and must come from the owning controller, not wall-clock time.

Min/ceiling are mandatory reviewed inputs. No default runtime or rate estimate.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

FIRST = "FIRST_MEANINGFUL_FULL_ATTEMPT"
ROOT_SCHEMA = "GDN32_FULL_MODEL_SAME_JOB_BINDING_V1"
POLICY_SCHEMA = "GDN32_FIRST_MEANINGFUL_POLICY_V1"
BUILD_SCHEMA = "GDN32_FIRST_BUILD_ADMISSION_V1"
DERIVATION_SCHEMA = "GDN32_FIRST_DERIVED_RUNTIME_V1"
SCOPE = "GDN32_FULL_M128_MODEL_EVALUATION_NOT_FINAL_RTL"
JOB_SECONDS = 21000
BUILD_CAP_SECONDS = 7200
CENSUS_SECONDS = 30
CONTROL_SECONDS = 60
HOST_PHASES = {"postprocess": 1800, "evidence_verification": 1800,
               "summary_verification": 3600, "rss_telemetry_verification": 1800}
NON_DUT_WORK_SECONDS = 120 + 120 + 180 + 120
NON_DUT_OVERHEAD_SECONDS = 4 * 60
DUT_OVERHEAD_SECONDS = 30 + 30 + 30
PARENT_SECONDS = 600
FIXED_TAIL_SECONDS = sum(HOST_PHASES.values()) + NON_DUT_WORK_SECONDS + NON_DUT_OVERHEAD_SECONDS + DUT_OVERHEAD_SECONDS + PARENT_SECONDS
DUT_START_TAIL_SECONDS = sum(HOST_PHASES.values()) + DUT_OVERHEAD_SECONDS + PARENT_SECONDS
NECESSARY_ACTIVE_CYCLES = 21516288
MAX_ACTIVE_CYCLES = 1000000000
ORIGINAL_CAPS = {"archives": 600, "weights": 3600, "install": 180,
                 "owner_bind": 120, "reference": 180, "provider": 180,
                 "build": BUILD_CAP_SECONDS, "parent": PARENT_SECONDS}
POLICY_FIELD = "first_attempt"
DERIVATION_FIELD = "first_meaningful_derivation"
BUILD_FILENAME = "FIRST_MEANINGFUL_BUILD_ADMISSION.json"
DERIVED_FILENAME = "FIRST_RUNTIME_CONTROLLER.json"
START_FILENAME = "FIRST_MEANINGFUL_DUT_START.json"


def need(condition, message):
    if not condition:
        raise ValueError(message)


def same(left, right):
    return json.dumps(left, sort_keys=True, allow_nan=False, separators=(",", ":")) == json.dumps(right, sort_keys=True, allow_nan=False, separators=(",", ":"))


def positive_int(value, name):
    need(type(value) is int and value > 0, name + " must be a positive integer")
    return value


def finite_clock(value, name):
    need(type(value) in (int, float) and math.isfinite(value) and value >= 0,
         name + " must be a finite nonnegative monotonic observation")
    return value


def canonical(value, exists=True):
    path = Path(value)
    need(path.is_absolute() and path == path.resolve(), "canonical absolute path")
    need(all(not p.is_symlink() for p in (path, *path.parents)), "no symlink in pinned path")
    if exists:
        need(path.is_file(), "pinned regular file required")
    return path


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@dataclass(frozen=True)
class Pin:
    path: str
    bytes: int
    sha256: str

    @classmethod
    def parse(cls, row):
        need(type(row) is dict and set(row) == {"path", "bytes", "sha256"}, "exact pin fields")
        need(type(row["path"]) is str and type(row["bytes"]) is int and row["bytes"] >= 0, "pin types")
        h = row["sha256"]
        need(type(h) is str and len(h) == 64 and all(c in "0123456789abcdef" for c in h), "sha256 hex")
        return cls(**row)

    def row(self):
        return {"path": self.path, "bytes": self.bytes, "sha256": self.sha256}

    def verify(self, cap=None):
        path = canonical(self.path)
        need(cap is None or self.bytes <= cap, "pin size cap")
        need(path.stat().st_size == self.bytes and sha(path) == self.sha256, "pinned bytes changed")
        return path


def file_pin(path):
    path = canonical(str(path))
    return Pin(str(path), path.stat().st_size, sha(path))


def unique(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError("nonfinite JSON constant " + value)


def read_json(pin):
    need(type(pin) is Pin, "explicit immutable input pin")
    path = pin.verify(16 << 20)
    value = json.loads(path.read_text(), object_pairs_hook=unique, parse_constant=reject_constant)
    need(type(value) is dict, "JSON object required")
    return value


def write_new(path, value):
    path = canonical(str(path), exists=False)
    need(path.parent.is_dir(), "existing owned binding directory required")
    # x prevents accidental retry/restart. Failed or interrupted writes remain a
    # blocker; never overwrite, delete, or reuse one to retry a native phase.
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, allow_nan=False, separators=(",", ":"))
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    return file_pin(path)


@dataclass(frozen=True)
class FirstPolicy:
    min_dut_wall_seconds: int
    max_dut_wall_seconds: int
    min_build_window_seconds: int
    reviewed_plan: Pin

    def __post_init__(self):
        positive_int(self.min_dut_wall_seconds, "min_dut_wall_seconds")
        positive_int(self.max_dut_wall_seconds, "max_dut_wall_seconds")
        positive_int(self.min_build_window_seconds, "min_build_window_seconds")
        need(self.min_build_window_seconds <= BUILD_CAP_SECONDS, "reviewed minimum build window exceeds original 7200 cap")
        need(self.min_dut_wall_seconds <= self.max_dut_wall_seconds <= JOB_SECONDS - FIXED_TAIL_SECONDS,
             "reviewed min/ceiling must fit original job with complete fixed tail")
        need(type(self.reviewed_plan) is Pin, "reviewed plan pin required")

    def row(self):
        return {"schema": POLICY_SCHEMA, "policy": FIRST, "selected_profiles": [1],
                "min_dut_wall_seconds": self.min_dut_wall_seconds,
                "max_dut_wall_seconds": self.max_dut_wall_seconds,
                "min_build_window_seconds": self.min_build_window_seconds,
                "post_freeze_control_seconds": CONTROL_SECONDS,
                "cpu_seconds_equal_wall_seconds": True, "max_active_cycles": MAX_ACTIVE_CYCLES,
                "meaningful_goal": {"pc_at_least": 7, "completions_at_least": 7,
                                    "reset_after_start_allowed": False,
                                    "necessary_active_cycles": NECESSARY_ACTIVE_CYCLES,
                                    "completion_guaranteed": False},
                "reviewed_plan": self.reviewed_plan.row()}

    @classmethod
    def parse(cls, row):
        need(type(row) is dict and all(k in row for k in ("min_dut_wall_seconds", "max_dut_wall_seconds", "min_build_window_seconds", "reviewed_plan")),
             "reviewed min and ceiling unresolved: no default runtime allowed")
        result = cls(row["min_dut_wall_seconds"], row["max_dut_wall_seconds"], row["min_build_window_seconds"], Pin.parse(row["reviewed_plan"]))
        need(same(row, result.row()), "exact immutable P1 FIRST policy")
        return result


def validate_policy(row):
    """No defaults; unresolved/null reviewed fields are an admission blocker."""
    return FirstPolicy.parse(row)


def elapsed(root, now, *, last_observed_monotonic):
    start = finite_clock(root["job_started_monotonic"], "original job start")
    finite_clock(now, "now")
    finite_clock(last_observed_monotonic, "last observation")
    need(start <= last_observed_monotonic <= now, "stale/backwards/original-clock reset")
    value = now - start
    need(value < JOB_SECONDS, "original 21000 second job expired")
    return value


def validate_root(root, *, verify_files=True):
    need(root.get("schema") == ROOT_SCHEMA and DERIVATION_FIELD not in root, "unmodified root controller required")
    need(root.get("execution_mode") == "FULL_BLOCK_ACCEPTANCE" and same(root.get("profiles"), list(range(5))), "original full hardware/program")
    need(root.get("tokens") == 128 and root.get("matrix_macs") == 4096 and root.get("vector_lanes") == 32, "fixed M128 geometry")
    need(root.get("payload_uploads") is False and root.get("final_rtl_replay") is False, "no upload/final RTL authority")
    need(all(root.get(k) is None for k in ("cloud_binding", "builder_handoff", "model_candidate_review", "host_diagnostic",
                                         "host_profile_driver", "finite_long_policy", "stage_coverage_budget")), "no borrowed old artifact authority")
    need(root.get("dut_rss_bytes") == 8 << 30 and root.get("numeric_reserved_increment_bytes") == 512 << 20, "unchanged memory limits")
    need(type(root.get("budgets")) is dict and all(type(root["budgets"].get(k)) is int and root["budgets"][k] == v for k, v in ORIGINAL_CAPS.items()), "unchanged original stage caps")
    d = root["gdn32_full"]
    need(d["selected_profiles"] == [1] and all(type(i) is int for i in d["selected_profiles"]), "P1 only")
    need(same(d["registered_profiles"], list(range(5))) and d["tokens"] == 128 and d["scope"] == SCOPE, "unchanged full scope")
    need(d["job_budget_seconds"] == JOB_SECONDS and d["completion_guaranteed"] is False, "original finite whole-job clock")
    need(d["execution_policy"] == "FULL_PROGRAM_FINITE_WATCHDOG_NO_SHORT_FALLBACK" and d["lifecycle_policy"] == FIRST, "explicit FIRST admission only")
    positive_int(d["bootstrap_seconds"], "bootstrap_seconds")
    need(d["bootstrap_seconds"] <= 1800, "original bootstrap cap")
    policy = FirstPolicy.parse(root["gdn32_full"][POLICY_FIELD])
    need(policy.min_build_window_seconds >= d["bootstrap_seconds"], "reviewed build minimum must cover original bootstrap")
    need(type(d["profiles"]) is dict and set(d["profiles"]) == {"1"}, "single P1 watchdog")
    p = d["profiles"]["1"]
    expected_fields = {"wall_seconds", "cpu_seconds", "max_active_cycles", "log_raw_bytes", "rss_telemetry_raw_bytes",
                       "log_compressed_bytes", "rss_telemetry_compressed_bytes"} | {phase + "_" + kind + "_seconds" for phase in HOST_PHASES for kind in ("wall", "cpu")}
    need(set(p) == expected_fields and all(type(v) is int and v > 0 for v in p.values()), "unchanged exact finite watchdog fields")
    need(p["wall_seconds"] == p["cpu_seconds"] == policy.max_dut_wall_seconds and p["max_active_cycles"] == MAX_ACTIVE_CYCLES, "root declares reviewed ceiling and original cycle cap")
    need(p["log_raw_bytes"] <= 16 << 30 and p["rss_telemetry_raw_bytes"] <= 16 << 30 and p["log_compressed_bytes"] <= 64 << 20 and p["rss_telemetry_compressed_bytes"] <= 64 << 20, "original log/telemetry quotas")
    need(all(p[phase + "_" + kind + "_seconds"] == cap for phase, cap in HOST_PHASES.items() for kind in ("wall", "cpu")), "all four 9000 second host phases preserved")
    finite_clock(root["job_started_monotonic"], "original start")
    need(type(root.get("first_attempt_clock_id")) is str and root["first_attempt_clock_id"], "owning original monotonic epoch identity")
    canonical(root["job_root"], exists=False)
    need(type(root.get("pins")) is dict and root["pins"], "original source closure required")
    if verify_files:
        plan = read_json(policy.reviewed_plan)
        need(plan.get("schema") == "GDN32_FIRST_REVIEWED_WINDOW_PLAN_V1" and plan.get("selected_profiles") == [1]
             and plan.get("min_dut_wall_seconds") == policy.min_dut_wall_seconds and plan.get("max_dut_wall_seconds") == policy.max_dut_wall_seconds
             and plan.get("min_build_window_seconds") == policy.min_build_window_seconds
             and plan.get("post_freeze_control_seconds") == CONTROL_SECONDS,
             "pin must identify reviewed plan with identical explicit min/ceiling")
        for path, digest in root["pins"].items():
            need(sha(canonical(path)) == digest, "original source pin drift")
        helper = str(Path(__file__).resolve())
        need(root["pins"].get(helper) == sha(helper), "helper must be independently source-pinned")
        Pin.parse(d["source_catalog"]).verify(4 << 20)
    return policy


def remaining_after_build(policy):
    need(type(policy) is FirstPolicy, "immutable FIRST policy required")
    return policy.min_dut_wall_seconds + FIXED_TAIL_SECONDS + CONTROL_SECONDS


def build_window(root, now, *, last_observed_monotonic):
    policy = validate_root(root, verify_files=False)
    remaining = JOB_SECONDS - elapsed(root, now, last_observed_monotonic=last_observed_monotonic)
    cap = min(BUILD_CAP_SECONDS, math.floor(remaining - remaining_after_build(policy) - CENSUS_SECONDS))
    need(cap >= max(root["gdn32_full"]["bootstrap_seconds"], policy.min_build_window_seconds), "NO_BUILD_ROOM_FOR_REVIEWED_BUILD_MINIMUM_DUT_AND_COMPLETE_TAIL")
    return cap


def runtime_window(root, freeze_monotonic, *, last_observed_monotonic):
    policy = validate_root(root, verify_files=False)
    window = min(policy.max_dut_wall_seconds,
                 math.floor(JOB_SECONDS - elapsed(root, freeze_monotonic, last_observed_monotonic=last_observed_monotonic) - FIXED_TAIL_SECONDS - CONTROL_SECONDS))
    need(window >= policy.min_dut_wall_seconds, "NO_DUT_ROOM_FOR_REVIEWED_MINIMUM_AND_COMPLETE_TAIL")
    return window


def check_clock(root, clock_id, now, previous):
    need(clock_id == root["first_attempt_clock_id"], "monotonic epoch changed")
    elapsed(root, now, last_observed_monotonic=previous)


def _material_pins(rows, job):
    need(type(rows) is dict and set(rows) == {"materials", "reference"}, "exact completed materials/reference pins")
    for role, row in rows.items():
        p = Pin.parse(row)
        path = p.verify()
        need(path.is_relative_to(job) and path != job, "fresh same-job " + role + " evidence")
    return copy.deepcopy(rows)


def begin_build(root_pin: Pin, *, material_reference_pins: Mapping, clock_id: str,
                observed_monotonic, last_observed_monotonic):
    """After all material/reference verification, once BEFORE census and build.

    This only writes an exclusive admission receipt and requires build/ absent.
    The original producer must still execute exactly once into that fresh path.
    """
    root = read_json(root_pin)
    validate_root(root)
    check_clock(root, clock_id, observed_monotonic, last_observed_monotonic)
    job = canonical(root["job_root"], exists=False)
    need(not (job / "build").exists(), "FRESH build path required; no old/restarted build")
    need(not (job / "bindings" / DERIVED_FILENAME).exists() and not (job / "bindings" / START_FILENAME).exists(), "no prior derivation/DUT")
    evidence = _material_pins(material_reference_pins, job)
    cap = build_window(root, observed_monotonic, last_observed_monotonic=last_observed_monotonic)
    receipt = {"schema": BUILD_SCHEMA, "root_controller": root_pin.row(), "clock_id": clock_id,
               "job_started_monotonic": root["job_started_monotonic"], "observed_monotonic": observed_monotonic,
               "previous_observed_monotonic": last_observed_monotonic, "build_root": str(job / "build"),
               "build_root_absent_before_start": True, "materials_reference_pins": evidence,
               "effective_build_seconds": cap, "remaining_after_build_seconds": remaining_after_build(FirstPolicy.parse(root["gdn32_full"][POLICY_FIELD])),
               "census_reserved_seconds": CENSUS_SECONDS, "native_started_by_helper": False}
    return write_new(job / "bindings" / BUILD_FILENAME, receipt)


def _verify_build_admission(root, root_pin, admission_pin):
    job = Path(root["job_root"])
    need(admission_pin.path == str(job / "bindings" / BUILD_FILENAME), "fixed original build admission path")
    admission = read_json(admission_pin)
    need(set(admission) == {"schema", "root_controller", "clock_id", "job_started_monotonic", "observed_monotonic", "previous_observed_monotonic", "build_root", "build_root_absent_before_start", "materials_reference_pins", "effective_build_seconds", "remaining_after_build_seconds", "census_reserved_seconds", "native_started_by_helper"}, "exact build admission fields")
    need(admission["schema"] == BUILD_SCHEMA and admission["root_controller"] == root_pin.row(), "original pinned build admission")
    need(admission["job_started_monotonic"] == root["job_started_monotonic"] and admission["clock_id"] == root["first_attempt_clock_id"], "build original clock")
    need(admission["build_root"] == str(job / "build") and admission["build_root_absent_before_start"] is True and admission["native_started_by_helper"] is False, "fresh build admission only")
    need(admission["effective_build_seconds"] == build_window(root, admission["observed_monotonic"], last_observed_monotonic=admission["previous_observed_monotonic"]), "recomputed initial build cap")
    need(admission["remaining_after_build_seconds"] == remaining_after_build(FirstPolicy.parse(root["gdn32_full"][POLICY_FIELD])) and admission["census_reserved_seconds"] == CENSUS_SECONDS, "complete tail plus separate census")
    _material_pins(admission["materials_reference_pins"], job)
    return admission


def _verify_build_result(root, result_pin):
    job = Path(root["job_root"])
    need(result_pin.path == str(job / "build/frontend/BUILD_ONLY_RESULT.json"), "immutable FRESH same-job build-result path")
    result = read_json(result_pin)
    manifest_pin = Pin.parse(result["artifact"]["manifest"])
    need(manifest_pin.path == str(job / "build/frontend/model_candidate_artifact/frozen_artifact.json"), "same newly built local manifest")
    manifest = read_json(manifest_pin)
    need(manifest.get("schema") == "MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1" and same(manifest.get("profiles"), list(range(5))) and same(manifest.get("artifact_identity"), root["artifact_identity"]), "actual owning build identity and all-five hardware")
    # The existing seven-file producer verifier is still mandatory. These bytes
    # are an identity binding, not proof of structural/numerical correctness.
    return manifest_pin


def _expected_derived(root, root_pin, admission_pin, build_result_pin, freeze_monotonic, previous):
    admission = _verify_build_admission(root, root_pin, admission_pin)
    need(previous >= admission["observed_monotonic"], "freeze precedes original build admission")
    window = runtime_window(root, freeze_monotonic, last_observed_monotonic=previous)
    need(freeze_monotonic - admission["observed_monotonic"] <= admission["effective_build_seconds"] + CENSUS_SECONDS,
         "original one-build-plus-census cap exceeded")
    manifest_pin = _verify_build_result(root, build_result_pin)
    derived = copy.deepcopy(root)
    derived["gdn32_full"]["profiles"]["1"]["wall_seconds"] = window
    derived["gdn32_full"]["profiles"]["1"]["cpu_seconds"] = window
    derived[DERIVATION_FIELD] = {"schema": DERIVATION_SCHEMA, "parent_controller": root_pin.row(),
                               "build_admission": admission_pin.row(), "build_result": build_result_pin.row(),
                               "artifact_manifest": manifest_pin.row(), "materials_reference_pins": admission["materials_reference_pins"],
                               "clock_id": root["first_attempt_clock_id"], "job_started_monotonic": root["job_started_monotonic"],
                               "freeze_monotonic": freeze_monotonic, "previous_observed_monotonic": previous,
                               "elapsed_at_freeze_seconds": freeze_monotonic - root["job_started_monotonic"],
                               "fixed_tail_seconds": FIXED_TAIL_SECONDS, "post_freeze_control_seconds": CONTROL_SECONDS, "derived_dut_wall_seconds": window,
                               "derivation_count": 1, "native_started_by_helper": False}
    return derived


def freeze_controller(root_pin: Pin, build_admission_pin: Pin, build_result_pin: Pin, *,
                      clock_id: str, freeze_monotonic, last_observed_monotonic):
    """Exactly once after build success, before any DUT; never adjust a live DUT."""
    root = read_json(root_pin)
    validate_root(root)
    check_clock(root, clock_id, freeze_monotonic, last_observed_monotonic)
    job = Path(root["job_root"])
    need(not (job / "bindings" / START_FILENAME).exists(), "DUT already claimed; no extension/restart")
    derived = _expected_derived(root, root_pin, build_admission_pin, build_result_pin, freeze_monotonic, last_observed_monotonic)
    return write_new(job / "bindings" / DERIVED_FILENAME, derived)


def verify_derived(derived_pin: Pin, *, expected_root_pin: Pin, expected_build_admission_pin: Pin,
                   expected_build_result_pin: Pin, clock_id: str, observed_monotonic,
                   last_observed_monotonic):
    """Recompute derivation using trusted parent/evidence pins, never self-asserted authority.

    May verify after start, but cannot change runtime or authorize another start.
    Caller supplies an actual current observation and persisted high-water mark.
    """
    root = read_json(expected_root_pin)
    validate_root(root)
    check_clock(root, clock_id, observed_monotonic, last_observed_monotonic)
    need(derived_pin.path == str(Path(root["job_root"]) / "bindings" / DERIVED_FILENAME), "fixed derived binding path")
    derived = read_json(derived_pin)
    provenance = derived[DERIVATION_FIELD]
    freeze = finite_clock(provenance["freeze_monotonic"], "freeze")
    need(freeze <= observed_monotonic, "future freeze or stale verification clock")
    expected = _expected_derived(root, expected_root_pin, expected_build_admission_pin,
                                 expected_build_result_pin, freeze, provenance["previous_observed_monotonic"])
    need(same(derived, expected), "derived binding tamper: only exact watchdog wall/cpu and provenance may differ")
    return derived


def verify_derived_document(derived, *, expected_derived_pin: Pin, **verification):
    """For loaded bridge controllers: verify external pin first, then exact object.

    Do not compute expected pins from untrusted provenance; recover them from
    the already admitted owning invocation / flow handoff.
    """
    checked = verify_derived(expected_derived_pin, **verification)
    need(same(derived, checked), "loaded derived document differs from pinned binding")
    return checked


def claim_dut_start(derived_pin: Pin, **verification):
    """One-shot start marker only. Existing outer/resource/native gates still apply.

    Invoke after the four selected non-DUT steps, before consumer preflight.
    A failed or stopped attempt keeps this marker and cannot be restarted.
    """
    derived = verify_derived(derived_pin, **verification)
    now = verification["observed_monotonic"]
    window = derived["gdn32_full"]["profiles"]["1"]["wall_seconds"]
    left = JOB_SECONDS - (now - derived["job_started_monotonic"])
    need(left >= window + DUT_START_TAIL_SECONDS, "NO_COMPLETE_DUT_AND_HOST_TAIL_AT_START")
    path = Path(derived["job_root"]) / "bindings" / START_FILENAME
    return write_new(path, {"schema": "GDN32_FIRST_DUT_START_CLAIM_V1", "derived_controller": derived_pin.row(),
                            "parent_controller": verification["expected_root_pin"].row(),
                            "observed_monotonic": now, "clock_id": verification["clock_id"],
                            "dut_wall_seconds": window, "dut_cpu_seconds": window,
                            "start_count": 1, "native_started_by_helper": False})


def meaningful_goal_observed(*, pc, completions, reset_after_start):
    """Progress predicate only; never returns a FULL/RTL/numerical PASS label."""
    need(type(pc) is int and pc >= 0 and type(completions) is int and completions >= 0 and type(reset_after_start) is bool,
         "typed actual progress/reset observation")
    return pc >= 7 and completions >= 7 and not reset_after_start
