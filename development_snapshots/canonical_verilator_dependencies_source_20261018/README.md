# Reproduce fixed Verilator build-dependency acquisition

This is portable SOURCE for acquiring exactly five official Debian package byte strings totaling2466616B. It stops before package extraction, installation or execution. Official URLs, sizes and SHA256 pins are in worker/DEPENDENCY_PLAN.json. No package bodies, raw actual logs, machine paths, current system inventory or credentials are included.

Production run_gate.py, GATE_PLAN.json, worker/acquire_dependencies.py, worker/DEPENDENCY_PLAN.json and worker/published_acquire.py retain the exact bytes independently reviewed and used for the observed acquisition. GATE_PLAN.worker_manifest is historical source-provenance metadata, not a runtime dependency or a claim that the excluded original local manifest is shipped. Runtime source paths and pins are fully listed by INSTALL_MAP.json.

## Invocation

From a restored repository, set REPO to its explicit absolute root and SOURCE to this directory. SOURCE preflight:

    python -I -S -B "$SOURCE/run_gate.py" --repo "$REPO" --worker-source "$SOURCE/worker"

Cold tests, each also with -O:

    python -I -S -B "$SOURCE/test_gate_cold.py" --repo "$REPO" --worker-source "$SOURCE/worker"
    python -I -S -B "$SOURCE/worker/test_dependency_cold.py" --repo "$REPO"

Cold tests use only tiny synthetic bytes and process/network mocks. Direct script entry never loads project pyc. The portable worker cold entry now explicitly rejects source size/SHA drift before compile under both normal and -O, requires the isolated flags before project loading, and takes --repo instead of a machine path. See PROJECTION_DELTA.json. These changes do not alter production acquisition logic or retroactively change the frozen original cold entry.

For a new actual attempt, an owner must first verify this source manifest and fixed repository dependencies, independently review the exact binding, then execute the fixed run_gate.py through a same-buffer size/SHA-verified compile/exec loader using --output FRESH_ABSOLUTE_OUTPUT --execute-reviewed-acquisition. Preserve the original outer exit and elapsed time. A package receipt or RESULT alone never establishes success.

## Boundaries

Shared180s: preflight latest10, work maximum160/latest170, cleanup5 and postflight within180. Child CPU160s, one allowed core, AS512MiB, CORE0 and per-file FSIZE4MiB. Socket30, no redirects or retry; per-package<2MiB and shared transfer4MiB. Log64KiB is a post-run soft acceptance bound. Default platform environment/TLS/proxy route is inherited without modification or logging. No fallback or credential handling.

The original fixed WNOWAIT supervisor retains the unreaped process anchor, private group kill-before-reap cleanup and group-absence verification. Three worker source files are frozen into a fresh output and all original/snapshot sources are posthashed. Exactly five0600 byte strings and ACQUISITION.json must remain and each is posthashed. Leftover partial/cleanup files leave the outer qualification incomplete without erasing evidence.

RESULT is EVIDENCE_PENDING_OUTER_EXIT0, terminal_success=false. Acceptance requires original outer exit0 within180s, cleanup, exact bytes and independent actual review. SAFE_HISTORY.json records only the observed local run; its actual-review PENDING_AT_FREEZE is immutable historical state, to be cross-referenced by later publication/actual review. This provides no tool startup, build, hierarchy, DPI, Host execution or numerical qualification.
