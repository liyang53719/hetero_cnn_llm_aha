# Local-agent handoff v6.3

State: Revision 7 lane/equivalence/real E1 PASS; structural H3 FAIL_TIMING.
Revision 8A candidate is source-ready and approved for bounded local gates.

## Accepted evidence

- L5.1 Block128 E1/E4 accepted; WNS `+0.0000136495 ns`, component-level only.
- L5.2 real 16x32/512-lane E1 accepted: 1,000,000 dependent issues at II=1 and 10,000 random-backpressure operations.
- Revision-7 source-remapped lane WNS `+0.000141501 ns`, zero unmapped/unresolved.
- Revision-7 zero-delay mapped gate comparison: 120,032 samples, zero mismatch/unknown.

## Revision-7 failure

Structural H3 fails:

```text
WNS       -0.926028 ns
TNS       -49161.85 ns
unmapped  0
unresolved 0
lanes     512, one lane variant
```

The path is scheduler FIFO/completion state → same-cycle bypass → global
broadcast → lane accumulator mux → HardFloat Pre. Do not retry Revision 7.

## Revision 8A candidate

Revision 8A writes each rounded result into its lane-local context bank when
Post advances into Output. The four banks are therefore also the output-stage
registers. Architectural completion, busy/valid and external visibility still
occur only on output handshake. Same-context reissue reads the already-written
local bank; no completion/broadcast signal enters the FMA data path.

Implementation hierarchy:

```text
1 front-control DDC
  scheduler + elastic control + context tags
32 cluster16 DDC instances
  16 lanes each = 512 lanes
1 retained flag/reset glue DDC
```

Candidate source is under `rtl/matrix/candidates/rev8/`; canonical production
RTL is not replaced.

## Sandbox gates already passed

- Revision7-vs-Revision8A cycle model: 1,000,000 operations, exact public trace.
- 20 additional seeds / 500,000 operations: PASS.
- 500,612 same-cycle reuses in primary run.
- four contexts, four-cycle feedback, completion-to-Pre path absent by source check.
- Tcl/static flow: no multicycle, no synchronous-data false path, no retime.
- source-ready compare, E1, adversarial E1, lane/cluster/front/H3 and gate-compare scripts.

## Execute locally

```bash
./scripts/sandbox_validate.sh
python3 scripts/validate_l5_revision8a_contract.py --operations 100000
./scripts/run_l5_matrix_context_revision8a.sh compare
./scripts/run_l5_matrix_context_revision8a.sh e1
./scripts/run_l5_matrix_context_revision8a.sh adversarial
./scripts/run_l5_matrix_context_revision8a.sh lane
./scripts/run_l5_matrix_context_revision8a.sh equiv
./scripts/run_l5_matrix_context_revision8a.sh cluster
./scripts/run_l5_matrix_context_revision8a.sh front
./scripts/run_l5_matrix_context_revision8a.sh top
./scripts/run_l5_matrix_context_revision8a.sh e1
./scripts/run_l5_matrix_context_revision8a.sh adversarial
python3 scripts/summarize_l5_revision8a.py
```

A single `./scripts/run_l5_matrix_context_revision8a.sh all` performs the same
ordered flow.

## Stop rules

Only one normal and one high-effort attempt are allowed for lane, cluster and
front. Any negative component/H3 WNS, equivalence failure or E1 mismatch stops
Revision 8A. Do not add a fifth context/cycle, timing exception, retiming,
lower frequency, smaller array, or alternate cluster size without a new review.

L5.2 closes only if every check in
`reports/execution/l5_revision8a_local_result.json` is true. The result remains
component-level DC; L10 post-route/variation signoff stays open.

## Parallel work

L5.3 Blocked Attention cycle E0 remains accepted: q384 656,644 serialized
cycles, q1024 4,823,044 cycles and 43,008 summary merges, with no score or
probability DDR materialization. Real stream E1/E2 may proceed after or in
parallel with Revision 8A local execution.
