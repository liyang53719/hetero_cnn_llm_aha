# Default-off rectangular QK control cut

This candidate adds an independently instantiated Chisel adapter using the
unchanged production `MatrixStreamPort`. It is **not connected to HostBlockTop**.
Existing Scala owners, old Matrix profiles and non-emit readers are unchanged.
Constructor `enabled=false` drives no Matrix or B operation. An enabled start
also requires explicit legacy-owner quiescence. Arbitration is an integration
requirement, not established by a caller's Boolean.

## Implemented source contract

- A group has five contexts (stripe bases 0/5/10), or one context (base15), each
  with exactly eight steps. The adapter imposes round-robin context/step order.
  Group tags start at1 and strictly increment in one epoch until reset.
- Every step sets `emit=true`. Exactly one accepted step/result is outstanding;
  every real intermediate return is retired. A whole tile therefore needs
  128 returns, not16. The existing Matrix service's two FIFO tiles are not
  borrowed or reclassified as partial storage.
- Each returned payload is checked for finite FP32 only at selected causal
  coordinates. Padded rows/nonexistent keys are forced to BF16 +0; real future
  keys can remain nonfinite without poisoning selected cells. A return context
  or last mismatch poisons without accepting that mismatched return.
- A last return is captured in one16-KiB register tile. Its real32-byte word
  payloads use bank=row, word=context*32+column/8 in the existing B80-KiB layout.
  Only one write is accepted at a time; all selected-column writes must ACK
  before a slot is valid. Wrong ACK identity poisons while retaining the exact
  outstanding obligation. A successful ACK after poison still retires its real
  committed write, but never publishes a slot.
- Abort drains the accepted B write and the actual Matrix service terminal.
  The production Matrix service can suppress in-flight emitted output on abort;
  its tagged done certifies metadata drain. An independent service error done
  is accepted even without a payload return or a local abort. Local reset is
  not used as an ACK.
  Error completion locks the adapter until reset.
- Normal completion requires every partial's B commits and Matrix done. Reuse
  then waits for a separate tagged release certifying that the external ordered
  fold consumed all group slots. The fold itself is not implemented in Chisel
  here; a lying release producer is outside this adapter's trust boundary.

A688KiB/B80KiB and five accumulator contexts totaling80KiB are unchanged. The
candidate elaborates its own16-KiB capture register; final integration must reuse
Dense's existing finalValue or charge an additional16KiB. It is not already
wired to that register. No operand cache or extra partial tile is introduced.
The new B-word route, actual operand gather/ACK and legacy-owner arbitration
remain unconnected. The frozen phase model exercises actual numeric payloads
with bounded ACKs separately; it is not a Scala co-simulation.

## Scalar/fold/softmax resource boundary

The real Scalar request/result channel remains single-owner and variable latency
(`Qwen2Block.scala:98–114`, `BlockFloat.scala`). Every score still needs16 ordered
FP32 Adds from +0, dot BF16, FP32 scale `0x3db504f3`, then score BF16. Existing
internal Vector16 ALUs lack an external lending/flags interface; this candidate
does not invent one. Ordered softmax sum dependencies and iterative Exp/Div
remain. Scalar calls and Matrix issues are work counts, **not hardware cycles**.
Hardware cycles/utilization and whole-block performance remain null.

## Tests and bounded execution

`run_native.sh` builds the unchanged real native Matrix service once and runs
its32 legacy +10 existing rectangular-profile regressions, including non-emit,
old result readers, abort/epoch and one inherited accumulator resource. It also
runs the frozen9 numeric payload +8 ACK-phase tests. Native arithmetic tests
are host execution, not RTL. No business weights or full-block workload is used.

`run_control.sh` uses the original Chisel project and exact real port types,
adding only the candidate source/spec via transient sbt settings. Three unit
cases cover default-off, five-context/8-step progress with all320 B-word ACKs,
causal nonfinite selection, backpressure, wrong identity, abort and final
fold-release fencing. Matrix returns are controlled synthetic stimuli:
**CONTROL_ONLY means real RTL emission and Verilator simulation of the control
adapter; it does not mean Matrix arithmetic RTL was simulated.**

At preparation time no Scala compilation or RTL simulation has run locally;
sbt/Verilator are absent. The dedicated CI has one30-minute total job, the
existing official Java/sbt setup and HardFloat pin
`c1105e6ac6a0dd90fc80893efc4830ab609005d3`, and a20-minute control-test limit.
It triggers only on its own workflow path on main (or a manual request), only
run_attempt1, with independent concurrency. Publishing the final workflow is
the single planned activation; do not manually trigger a duplicate run.
`run_attempt` blocks reruns, but cannot technically prevent another new manual
dispatch; the single-run limit also requires this operator discipline. No production
Chisel path or old large-workflow trigger file is edited.

CI records source hashes, test summary, per-stage elapsed/status, and paths/hash
of emitted `.v/.sv` test RTL under `chisel/continuous_prefill/test_run_dir`.
A successful control result requires exactly three passed tests and a nonempty
generated RTL hash list. Only explicitly named summary/hash text files are artifacts. Native helper
reports, generated payloads, work directories and arbitrary metadata are never
uploaded. Actual full4096-MAC RTL is **NOT RUN**. If compilation exceeds the
budget, report its stage/diagnostic rather than enlarging the budget.
