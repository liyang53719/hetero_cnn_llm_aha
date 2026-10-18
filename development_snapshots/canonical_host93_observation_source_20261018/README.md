# Host93 startup and observed CLASS calibration source

This directory preserves reproducible Python source and pure cold tests. It contains no current tool inventory, dependency cache, actual execution logs, generated classes, or RTL. Execution code and cold tests are exact bytes of their reviewed source candidates. The safe historical summary qualifies only two fixed-version startup probes. Calibration actual remains PENDING in this projection; source review is not an actual compilation result. The earlier120-second CLASS attempt remains FAIL.

## Published source dependencies

Set REPO to the repository root containing these existing relative paths:

- `development_snapshots/canonical_host93_execution_source_20261018/class_compile/`: original reviewed CLASS source and CLASS_GATE_PLAN.json. Startup loads its fixed-SHA raw source, then verifies the plan and project-source pins.
- `development_snapshots/canonical_runtime_ram_source_20261018/run_behavior.py`: original WNOWAIT source selected by both gates.
- `development_snapshots/canonical_runtime_ram_source_20261018/test_runner_cold.py`: fixed raw source of the mock FakeOS class used by calibration cold tests.
- `candidates/qwen2_resident_matrix/host93_source_recovery/`: the new93 source plan and87-JAR acquisition plan.
- `candidates/qwen2_resident_matrix/production_qk16_rebase/classcompile/`: dependency pins and historical command provenance. Its old implementation is not executed by this source.

Exact project file bytes/hashes are in calibration/CLASS_GATE_PLAN.json and the previously published CLASS plan. No dependency search or union download is performed by these gates. Startup's `--class-gate` must point to the existing published CLASS directory above, not to calibration.

## Source-only cold commands

From this directory, with REPO explicitly provided:

    python -I -S -B startup/test_startup_cold.py
    python -I -S -B -O startup/test_startup_cold.py
    python -I -S -B calibration/test_class_gate_cold.py --repo "$REPO"
    python -I -S -B -O calibration/test_class_gate_cold.py --repo "$REPO"

The direct entries use fixed-SHA raw-byte compile/exec loaders and do not consult project pyc. Startup tests are all mocked; calibration tests use only mocks and synthetic temporary files. The original source reviews passed9+9 and23+23 respectively. Publication projection did not rerun tests or execute Java.

## Actual invocation contract

Actual runs require separately reviewed explicit Java, artifact cache, assembled-source, and fresh-output paths supplied by their executor. No local values are bundled here. Startup accepts --class-gate, --repo, --mode java-version or scala-version, --jar-artifacts, --java, --output, and --execute-reviewed-startup. Run each mode in a separate dedicated Python process with exactly one child. Calibration accepts --repo, --assembled-source, --jar-artifacts, --java, --output, and --execute-reviewed-class. Its default invocation with --repo alone is source preflight only.

One startup mode: total20 s, preflight4 s, child<=10 s ending by entry+14, original cleanup5 s, postflight by20. Calibration: total330 s, preflight20 s, compiler<=300 s ending by entry+320, original cleanup5 s, postflight by330. Same new93/87 profile, heap1 GiB, AS4 GiB, one CPU. Calibration's only compiler-option addition is -verbose. File hard limit48 MiB; log2 MiB and class-tree64 MiB are post-cleanup acceptance limits. JSONL observations are rate-limited to one per second, at most340 rows of2048 bytes. All resource limits and unchanged cleanup details are in code and SUPERVISOR_DELTA.json.

The version-only result does not instantiate Scala compiler Global. Verbose emits and flushes concrete progress messages, but does not guarantee every phase is reported or a2 MiB log ceiling. OFFICIAL_SOURCE_PINS.json and VERBOSE_EVIDENCE.md document the fixed official Scala2.13.16 sources and those limitations. No debug or deoptimization flag is enabled.

Observe only the original unreaped leader PID/starttime. CPU/RSS/HWM samples are process observations, not descendant/cgroup limits or proof of virtual-memory headroom. Terminal getrusage uses absolute Linux peak RSS, never a maxRSS delta. Missing measurements remain unknown. No measurement alone establishes OOM, a compiler phase, or compilation success.

Result files deliberately declare pending evidence and terminal_success=false. Actual outer exit0, externally saved elapsed within the same budget, complete original-group cleanup, input/postflight validation, and independent review are required for any stage qualification. Merely reusing these files or finding a result receipt grants none. This source never runs the Host emitter or produces RTL.
