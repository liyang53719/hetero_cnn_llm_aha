#!/usr/bin/env python3
"""Explicit one-stage runner; prepare never compiles or executes hardware.

The parent schedules every invocation. No automatic retry, cap increase,
parallel compile, full-top elaboration, cleanup, or dependency download.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ["HETERO_TEST_WORKSPACE"]).resolve(strict=True)
BINDING = ROOT / "p0_resident_fullcompile_recipe_20261030T1609/BINDING.json"
FROZEN = HERE.parents[1] / "fresh_original_top_recovery_20261028/source/TransposedDenseBanks.scala"
CANDIDATE = HERE.parent / "source/TransposedDenseBanks.scala"

def sha(p):
    with Path(p).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()

def strict(r):
    return (r.get("native_exit") == 0 and r.get("errors") == [] and
            (r.get("cleanup_proof") or {}).get("status") == "COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP" and
            (r.get("log_capture") or {}).get("pipe_eof_observed") is True and
            (r.get("log_capture") or {}).get("gzip_finalized") is True)

def write_new(path, value):
    with Path(path).open("x") as f:
        json.dump(value, f, indent=2)
        f.write("\n")

def prepare(run, variant):
    b = json.loads(BINDING.read_text())
    original_cp = b["argv"][b["argv"].index("-cp") + 1].split(":")
    # Existing cached jar aliases may point at verified recovered copies in /tmp.
    # Resolve once, pin actual regular bytes, and run using these exact paths.
    jars = sorted(set(str(Path(p).resolve(strict=True)) for p in original_cp))
    cp = ":".join(jars)
    trusted_aliases = {}
    def trusted_resolve(original):
        original = str(original)
        expected = b["pins"].get(original)
        if expected is None:
            raise ValueError("consumed tool is absent from trusted BINDING pins: " + original)
        resolved = Path(original).resolve(strict=True)
        if sha(resolved) != expected:
            raise ValueError("trusted original tool hash mismatch: " + original)
        trusted_aliases[original] = {"resolved": str(resolved), "sha256": expected}
        return str(resolved)
    for original in original_cp:
        trusted_resolve(original)
    plugin_arg = next(x for x in b["argv"] if x.startswith("-Xplugin:"))
    plugin = trusted_resolve(plugin_arg.split(":", 1)[1])
    java = trusted_resolve(b["argv"][0])
    source = CANDIDATE if variant == "candidate" else FROZEN
    sources = [source, HERE / "Slot2BankFixture.scala", HERE / "Slot2BankEmit.scala", HERE / "Slot2BankRegression.scala"]
    tools_root = ROOT / "verilator_dependency_recovery_20261030T0534/tools"
    manifest_path = ROOT / "verilator_dependency_recovery_20261030T0534/VERIFIED_TOOLS.json"
    v = json.loads(manifest_path.read_text())
    pins = {str(p): sha(p) for p in [*sources, *map(Path, jars), Path(plugin), Path(java),
                                  HERE / "run_stage.py", HERE / "tools/make", HERE / "tools/no_pch.mk", manifest_path,
                                  tools_root / "verilator", Path("/usr/bin/make"), Path("/usr/bin/g++").resolve()]}
    for row in v["files"]:
        p = Path(row["path"])
        if not p.is_file() or p.stat().st_size != row["bytes"] or sha(p) != row["sha256"]:
            raise ValueError("existing Verilator byte drift: " + str(p))
        pins[str(p)] = row["sha256"]
    supervisor = Path(b["supervisor_dir"])
    for name in ("supervise_multiroot.py", "strict_cleanup.py", "lossless_log.py"):
        p = Path(trusted_resolve(supervisor / name))
        pins[str(p)] = sha(p)
    base_caps = dict(b["caps"])
    # Separate bounded stages, never exceeding the inherited aggregate limits.
    caps = dict(base_caps, rss_bytes=min(base_caps["rss_bytes"], 1 << 30),
                file_bytes=min(base_caps["file_bytes"], 64 << 20),
                tree_bytes=min(base_caps["tree_bytes"], 256 << 20),
                watch_tree_bytes=min(base_caps["watch_tree_bytes"], 256 << 20),
                extra_watch_roots=[str(run)])
    stages = {}
    for stage, wall, cpu in (("compile", 90, 60), ("emit", 90, 60),
                             ("all", 240, 210), ("address", 240, 210), ("retention", 240, 210),
                             ("negative", 180, 150)):
        stages[stage] = dict(caps, wall_seconds=min(base_caps["wall_seconds"], wall),
                             cpu_seconds=min(base_caps["cpu_seconds"], cpu),
                             per_process_cpu_seconds=min(base_caps["per_process_cpu_seconds"], cpu))
    vm = [java, "-XX:-UsePerfData", "-XX:ActiveProcessorCount=1",
          "-XX:ReservedCodeCacheSize=128m", "-Xss4m", "-Xmx512m"]
    compile_argv = vm + ["-cp", cp, "scala.tools.nsc.Main", "-classpath", cp,
                         "-Xplugin:" + plugin, "-language:reflectiveCalls", "-d", ".", *map(str, sources)]
    model_vm = vm + ["-cp", str(run / "compile") + ":" + cp]
    plan = {
        "schema": "SLOT2_ACTUAL_BANK_REGRESSION_PLAN_V1", "variant": variant,
        "scope": "actual full-size bank component, not MAC/vector/owner/full-top acceptance",
        "source": str(source), "source_sha256": sha(source), "pins": pins,
        "trusted_tool_binding": str(BINDING), "trusted_tool_aliases": trusted_aliases,
        "supervisor_directory": str(supervisor), "caps": stages,
        "resource_gate": {"min_available_memory": 7 << 30, "min_disk_free": 8 << 30},
        "env": {"PATH": str(HERE / "tools") + ":" + str(tools_root) + ":/usr/bin:/bin",
                "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"},
        "argv": {"compile": compile_argv,
                 "emit": model_vm + ["chiseltest.simulator.jna.Slot2BankEmit", "emitted"],
                 **{s: model_vm + ["heteronpu.continuous.Slot2BankRegression", s]
                    for s in ("all", "address", "retention", "negative")}},
        "expected": {
            "candidate": "all stages pass with strict cleanup, no threshold changes",
            "baseline": "emit/address fail on 10-bit slot2 base; retention fails on actual A corruption after slot2 drain",
        },
        "hardware_capacity": {"a_banks": 16, "a_depth": 1376, "a_word_bits": 256,
                              "b_banks": 16, "b_depth": 160, "b_word_bits": 256},
        "full_top_dut_executed": False,
        "hardware_arithmetic_verified": False,
        "lease_owner_verified": False,
    }
    run.mkdir(parents=True, exist_ok=False)
    write_new(run / "PLAN.json", plan)
    print(json.dumps({"status": "PREPARED_NOT_EXECUTED", "plan": str(run / "PLAN.json"),
                      "source_sha256": plan["source_sha256"], "aggregate_rss_cap": 1 << 30}))

def execute(run, stage):
    plan_file = run / "PLAN.json"
    p = json.loads(plan_file.read_text())
    pins = dict(p["pins"])
    pins[str(plan_file)] = sha(plan_file)
    for name, digest in pins.items():
        if sha(name) != digest:
            raise ValueError("pinned input changed: " + name)
    if stage != "compile":
        result = json.loads((run / "compile/RESULT.json").read_text())
        if not strict(result):
            raise ValueError("compile did not strictly complete")
        for f in (run / "compile").rglob("*.class"):
            pins[str(f)] = sha(f)
    sys.path.insert(0, p["supervisor_directory"])
    import supervise_multiroot as supervisor
    r = supervisor.execute(p["argv"][stage], str(run / stage), str(HERE / "owner.lock"),
                           p["caps"][stage], p["env"], pins, resource_gate=p["resource_gate"])
    write_new(run / (stage + "_RETURN.json"), r)
    print(json.dumps({k: r.get(k) for k in ("native_exit", "errors", "elapsed_seconds", "observed_peak_rss")}))
    return 0 if strict(r) else 2

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("stage", choices=("prepare", "compile", "emit", "all", "address", "retention", "negative"))
    ap.add_argument("--run", required=True, help="new relative run label under tests/runs")
    ap.add_argument("--variant", choices=("candidate", "baseline"), default="candidate")
    args = ap.parse_args()
    if not args.run or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in args.run):
        ap.error("run label accepts only letters, digits, _ and -")
    run = HERE / "runs" / args.run
    if args.stage == "prepare":
        prepare(run, args.variant)
        return 0
    return execute(run, args.stage)

if __name__ == "__main__":
    sys.exit(main())
