# TEMP_SOURCE: one fixed Host93 CI coordinator

This is source for one reviewed GitHub job. No real acquisition, native build,
Host generation or runtime has occurred during its preparation. Component source
reviews remain separately bound; mock completion is not actual qualification.

## Invocation

    python3 -I -S -B candidates/host93_ci_recovery/run.py \
      --repo "$GITHUB_WORKSPACE" --out "$RUNNER_TEMP/host93-ci-private" \
      --idma-archive "$RUNNER_TEMP/host93-idma.zip" \
      --job-deadline "$HOST93_RUN_DEADLINE" --execute

The caller supplies a monotonic absolute deadline from the same runner host.
The workflow starts the common 6600-second clock before checkout/download and
passes start+6480 to this entry, leaving the last 120 seconds for validation and
safe upload. The entry uses min(passed deadline, its own entry+6600), and reserves
five seconds inside that bound for its evidence. Stage maxima never extend the
shared stop. Missing GitHub environment/deadline, blocked SIGALRM, a foreign
active timer, inadequate memory/disk or existing output fail closed. No retry is
performed. Without --execute, --repo and --out only verify fixed source pins.

The original supervisor's five WNOWAIT functions and four leader observers are
reused from fixed published source buffers. The small support v2 adds explicit
coordinator timer ownership: only its exact current handler and same absolute
deadline can be inherited; preparation is armed before creating phase state or
projecting the runner. The shared timer is restored with remaining time after
success or failure. Unowned or blocked timers are refused, never silently reset.
The original process-group/leader-anchor cleanup remains unchanged.

## Finite phases and observations

The component order is fresh patched official toolchain/tiny, fresh Host93
emission, fixed iDMA319, retained13, four fixed VLT configurations, then real
Host C++ generation, compilation and one reset/launch handshake. The exact
approved per-phase maxima are PHASE_CAPS in run.py; limits supplied by components
are checked again. The ten host tool probes use the new CI 30/10-second windows.
The long make is 3600/3570; Host generate600/540 and compile1800/1740 use AS6GiB;
Host run30/10 uses AS2GiB. Native CPU affinity is one allowed core. Per-file FSIZE
is hard, while tree/log totals are bounded postflight acceptance, not a claimed
OS aggregate-tree limit. Host generate/compile require MemAvailable8GiB and free
disk3GiB. The aggregate stage maxima can exceed the shared budget; completion is
not guaranteed, and the common wall always truncates them.

Stage records include original exit/cleanup only when the bounded call returns
that evidence. A caught failure without a returned record uses null exit and
cleanup=false, rather than inventing the child's result. RUSAGE_CHILDREN user/sys
CPU deltas can include descendants; leader sampling is not a full-tree sample.
The native logs, detailed usage, system tool identities, inputs and generated
artifacts stay private. Console output is only finite phase/status/seconds or an
error category. Platform proxy/CA values are handled only by acquisition
components and are never included in public evidence.

## Exactly three safe JSONs

    python3 -I -S -B candidates/host93_ci_recovery/run.py \
      --verify-evidence --out "$RUNNER_TEMP/host93-ci-private"

This entry reads only evidence/summary.json, evidence/source_hashes.json and
evidence/stage_exits.json. It runs no native code or component. It requires the
exact three regular files, no extra fields/unknown stages, bounded finite values,
project-relative source names and combined size at most1MiB. Unknown paths,
extra logs, weights/numerical claims, inconsistent successful stage tuples and
missing required stages are rejected. No RTL, archive, logs, system inventories,
ELF or tensor content may be uploaded.

READY_REQUIRES_ACTIONS_EXIT0 is explicitly nonterminal prepared evidence. It must
be combined with the actual original Actions execution step exit0; a leftover
file can never override a failed or timed-out job. INCOMPLETE evidence may be
uploaded after strict validation for diagnosis, while the failed step/job remains
failed. A hard kill may prevent evidence completion; absence is not success.
This job makes no N0 numeric, RAM-replay or full-block RTL assertion.

## Cold checks

    python3 -I -S -B test_run_cold.py
    python3 -I -S -B -O test_run_cold.py
    python3 -I -S -B test_support_v2_cold.py --repo /path/to/checkout
    python3 -I -S -B -O test_support_v2_cold.py --repo /path/to/checkout

The coordinator has49 tiny/mock cases in each mode, including a complete
synthetic stage traversal and a compile timeout whose safe evidence cannot mask
its exit1. Support v2 has21 cases per mode including armed preparation failure,
wrong-owner/timer rejection and preserved exception/remaining deadline. No phase
argv is executed by these tests. RUN_PINS fixes16 immediate component source/data
files; their own fixed manifests cover their published project dependencies.

The v2 evidence schema also reconstructs the canonical fixed source map digest from its public rows, without reading another file, and requires exact generated identities for the claimed scope. Fixed FIR/SV content digests are checked again in the upload validator.

The v3 path guard accepts only ASCII letters, digits, slash, underscore, dot and hyphen for complete caller paths before any source loader or native phase. Tabs, spaces, shell/make metacharacters and Unicode path bytes fail closed.
