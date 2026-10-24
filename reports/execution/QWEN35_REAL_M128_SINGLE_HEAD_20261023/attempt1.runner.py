import hashlib, json, os, resource, sys, time, unittest
from pathlib import Path
root = Path.cwd()
sys.path.insert(0, str(root))
out = root / "reports/execution/QWEN35_REAL_M128_SINGLE_HEAD_20261023"
plan = json.loads((out / "attempt1.plan.json").read_text())
def capture():
    return {p: dict(bytes=len(raw := (root / p).read_bytes()), sha256=hashlib.sha256(raw).hexdigest()) for p in plan["source_paths"]}
before = capture()
(out / "attempt1.sources_before.json").write_text(json.dumps(before, indent=2) + "\n")
bounds = dict(cpu_affinity=sorted(os.sched_getaffinity(0)), rlimit_as=resource.getrlimit(resource.RLIMIT_AS), rlimit_cpu=resource.getrlimit(resource.RLIMIT_CPU), OPENBLAS_NUM_THREADS=os.environ.get("OPENBLAS_NUM_THREADS"), OMP_NUM_THREADS=os.environ.get("OMP_NUM_THREADS"), python_bytecode_writes=not sys.dont_write_bytecode, external_wall_timeout_seconds=120)
assert len(bounds["cpu_affinity"]) == 1
assert bounds["rlimit_as"] == (536870912, 536870912)
assert bounds["rlimit_cpu"] == (120, 120)
assert bounds["OPENBLAS_NUM_THREADS"] == bounds["OMP_NUM_THREADS"] == "1"
assert not bounds["python_bytecode_writes"]
print(json.dumps(dict(checkpoint="verified_runtime_bounds", **bounds)), flush=True)
started = time.monotonic()
result = None
try:
    suite = unittest.defaultTestLoader.loadTestsFromName(plan["module"])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
finally:
    after = capture()
    (out / "attempt1.sources_after.json").write_text(json.dumps(after, indent=2) + "\n")
    changed = [p for p in before if before[p] != after[p]]
    receipt = dict(tests=None if result is None else result.testsRun, successful=False if result is None else result.wasSuccessful(), elapsed_seconds=time.monotonic()-started, peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, process_cpu_seconds=resource.getrusage(resource.RUSAGE_SELF).ru_utime+resource.getrusage(resource.RUSAGE_SELF).ru_stime, runtime_bounds=bounds, source_hashes_before_after_equal=not changed, changed_files=changed, captured_files=len(before), source_scope="Explicit files, not a full runtime dependency closure")
    (out / "attempt1.result.json").write_text(json.dumps(receipt,indent=2)+"\n")
    print(json.dumps(dict(checkpoint="attempt_receipt", **receipt)), flush=True)
sys.exit(0 if result is not None and result.wasSuccessful() and not changed else 1)
