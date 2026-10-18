# Host93 single observed SV calibration template

This source-only, explicitly unbound template retains the reviewed single-SV generation gate and its one observed calibration budget. No FIR, SV, tool binary, logs, absolute machine paths or system inventory are included. Execution differs from the reviewed calibration only in the fixed plan SHA; the cold entrypoint differs only in its corresponding raw-source SHA. All 29 cold tests, including six sampler boundary cases, are retained.

## Source checks and local binding

INSTALL_MAP.json lists all seven project-relative source/identity dependencies and direct `python -I -S -B` cold/preflight commands; repeat cold tests with `-O`. Dynamic project source is verified against exact raw-byte identity and compiled from the same buffer. No project bytecode loader is used. The existing class-stage descriptors are only inputs to the fixed supervisor projection: no Java, classes or JAR payload are loaded.

The template refuses actual execution before output creation. Machine-specific FIR and review paths, plus new tool-acquisition receipt/review slots, are PENDING. The 42,417,256-byte FIR SHA, official firtool 1.62.1 member SHA and 25,009,456-byte size, structure-review provenance, prior review hashes, flags and resource bounds remain fixed. Prior failed-actual and bound-SOURCE reviews are historical provenance; their preserved hashes are not fresh local execution authority.

Follow BINDING_REQUIREMENTS.json to prepare a separate local successor: establish exact same-FIR/tool evidence, independently review real acquisition and same-FIR structure, bind local receipts/paths, recompute plan/source/cold pins, cold-test and freeze for independent SOURCE review. A new attempt also requires separate authorization. Neither this template nor rebinding grants changed tool/FIR identities, relaxed checks, changed flags or another budget extension.

## Fixed calibration delta

The first 150-second Host attempt timed out. Its original failure remains preserved. The one calibration changes total180 to390 seconds, child wall150 to360 seconds, latest work stop entry+160 to entry+370, native CPU hard150 to360 seconds, and sampler maximum340 to400 rows. Preflight stays10 seconds and cleanup at most5 seconds; all postflight and final writing must finish before entry+390 seconds. AS2GiB, FSIZE128MiB and CPU affinity1 remain. Tree256MiB, log2MiB and annotation32MiB are postflight soft acceptance bounds, with at most64 inventory entries/32 files. These soft bounds are not OS tree hard limits.

The sampler is extracted from the exact same verified published source buffer. Its original fixed 1,925-byte function SHA is checked; only `state['count']<340` changes to `state['count']<400`, with reversible replacement. The original PID/starttime checks, one-second no-catchup schedule, proc helpers and immediate JSONL flush remain. HWM observations are recorded without assuming strict monotonicity; RUSAGE is the whole reaped child including preexec, not pass-specific metrics. The original five WNOWAIT lifecycle functions and kill-before-reap cleanup remain unchanged.

Fixed firtool flags retain all checking, including combinational-loop checking. The gate creates fresh private FIR/tool snapshots, leaves the acquired original tool0600 and makes only its new snapshot0700. Originals and snapshots are verified before and after successful execution. Unknown outputs, binding errors, timeout or resource failure preserve the attempt. Another timeout stops native retries and budget extension and leads only to read-only pass-source complexity diagnosis.

Every RESULT is nonterminal evidence. Acceptance requires the original outer exit0, actual elapsed within390 seconds, successful complete postflight and independent actual review of the full final inventory. This stage qualifies only RTL generation and inventory. Same-SV Host83/resource8/tap structure, simulation, Host execution, C++tap bindings and numerical behavior remain separate. No lost historical95 or old Kernel identity is inherited.

SAFE_HISTORY.json is finalized only after the original calibration handle reaches a real terminal state. It records the observed outcome and the actual-review state at source freeze; it cannot turn an incomplete stage into a success.
