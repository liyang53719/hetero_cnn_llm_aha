# Bounded FIFO and opaque-handshake diagnostics

Status: TEMP_SOURCE; SOURCE v2 GO; actual job NOT_EXECUTED.

This isolated candidate adds one small-job entry. It first compiles and runs the pinned FIFO local four-state/next-state miter using staged official Icarus 12.0-2build2. Only after that succeeds does it reuse the existing fixed Verilator source/build/tiny qualification once, followed by transparent and opaque eight-leaf generation cases. It does not acquire Scala/JARs/FIR, regenerate the complete Host, or run Host C++ or numerical workloads. The existing tool's small C++ compile/run qualification remains part of its unchanged 20 stages.

The FIFO fixture compares 5,180 settled observations across Depth 2/3 and SameCycleRW 0/1, including directed X/Z cases and manually stepped backpressure/order traces. Its original and derived combinational regions are exact projections of the fixed FIFO source. It does not prove register-macro/reset/clock/delta-cycle equivalence or close the three original iDMA warnings.

The Host pair is a state-cut MODEL. Both cases preserve atomic all-leaf ready/valid gates and real output-ready to step-ready dependence. The opaque leaf has one all-input/four-output DPI call; it is hand-authored, has no executable DPI implementation, and is not the actual 22-input/21-output generated wrapper. Transparent success plus an opaque natural warning-fatal exit is accepted only when every diagnostic warning is UNOPTFLAT, its count matches the sole final warning-fatal summary, and a bounded Example-path witness connects the fixed combo block and atomic handshake. This is a model observation, not a production warning exemption or behavioral equivalence result.

All 25 stages share the pre-checkout work deadline. Warning-fatal remains enabled; other errors, timeouts, cleanup failures, missing identities, library failures, and unexpected output stop the job. Only three validated, bounded evidence JSON files are publishable. Private logs, package/tool files, generated code, and host library identities remain private.

Independent SOURCE acceptance: review_host_micro_job_source_v2_20261019T0621, MANIFEST SHA256 f1b32efd6d010ab67984d86730dbd339532e4e889b7a9170c4f5f9bd569edd01; SUMMARY SHA256 c7e8cb9221b88a2114201173b56822a33f2c92138cf837f8baef42ad15f60bb6. Verdict: SOURCE_GO_FINITE_25_STAGE_FIFO_AND_MODELED_HOST_MICRO_JOB. Actual remains NOT_EXECUTED.
