# PV GQA packing: geometry and capture specification, blocked candidate

This isolated stdlib package contains a geometry/capacity screen and a bounded
capture/credit behavior specification. It does not change an existing owner,
execute floating point, borrow a live resource, run RTL, or claim performance.
The geometry report says `STATIC_ONLY_CANDIDATE_BLOCKED`; the behavioral report
says `BEHAVIOR_SPEC_ONLY_CANDIDATE_BLOCKED`.

## Proposed isolated next gate

For one KV head, flatten `(query, its six Q heads)` in query-major order and
group 32 rows. Reuse the existing default-off transposedDense routing: `a[0:16]`
holds 16 normalized BF16 probabilities, `b[128:144]` the next 16,
`b[0:128]` the shared BF16 V vector, and `b[144:256]` zeros. Physical cell
`(r, d+128*half)` is logical probability row `r+16*half`, dimension `d`.
Each retained output follows the original ascending causal-key FMA order.

Sources: `transposed_down/numeric_smoke.cpp:59-75` and
`transposed_route/transposed_mode.patch:7-15,61-79`, under the sibling
`qwen2_resident_matrix` directory. That route is a candidate and currently only
accepts transposed opcode0x20. It is not an existing Qwen2 Attention mode.

M128 has 768 query/head rows per KV head and 24 groups32 per head:

- PV issues = `2 * sum(ceil(32*g/6), g=1..24) = 3216`
- Useful PV FMA = `12 * 128*129/2 * 128 = 12681216`
- PV useful / fixed4096 issued opportunities = `129/134 = 96.2686567%`
- Every one of 1536 query/head rows must be captured exactly at key=query;
  this requires288 wide emitted snapshots if emitting only at row-final keys

This percentage is only issued geometry. It omits recurrence stalls, operands,
capture, softmax, all acknowledgements, QK, Dense, and the rest of the block.

## Why this cannot close the full-block goal

Leaving QK unchanged still costs `99072*8 = 792576` Matrix issues. Seven ideal
Dense matrices require `1462272` issues for `5989466112` useful FMA. Including
Attention, whole useful FMA is `6014828544`. Even if PV and every other operation
were free, one shared4096 Matrix therefore gives:

`6014828544 / (4096 * (1462272+792576)) = 65.1247446%` upper bound.

Adding just this candidate's3216 PV issues tightens it to65.0319920%. These are
optimistic mathematical bounds, not cycle predictions. Five contexts cannot
issue five wide operations per cycle. The unchanged full-block runner also
records2651136 original accepted wide steps, consistent with its
1462272 Dense +1188864 original Attention steps.

## Fixed capacity and actual missing interfaces

Existing A is16 banks*1376 words*32B =704512B; B is16*160*32B =81920B.
Accumulator storage remains5*16*256*4 =81920B. No new MAC, SRAM or context is
proposed. One KV head's K/V is65536B, fitting A banks0..7 words0..255. The
intended preparation computes QK/softmax one row at a time in the existing
owner's128-word Q buffer and two max1024-word score/probability buffers; these
already-existing512B/8192B allocations remain explicit. Completed normalized
probabilities move to the new B-bank layout. Parallel QK producers are not
assumed; any wider producer would need a new live-storage and port ledger.

Five32-row probability cohorts, each128 keys of BF16, use40960B: each cohort
uses a distinct pair of B banks, words0..127. One shared16KiB output capture
uses all16 B banks at words128..159. Total B use is57344B. There is no private
capture per context. A PV gather needs one read from each of8 A banks plus two
B-bank reads; a proposed512B capture row needs one write to each of16 B banks.
The test checks only1R1W capacity and disjoint addresses. The new all-bank write
routing is not implemented or costed; existing interfaces cannot be assumed to
provide this bandwidth. Current Dense must be idle and fully drained before an
explicit lease, and the lease must survive until all relevant output ACKs.

Blocking issues:

1. `td_step` requires aligned16 group boundaries and `emit==last`; arbitrary
   causal lengths and intermediate row-final returns are not implemented.
2. Capture must follow the returning `(cohort, context, key)` identity, before
   later padded suffix FMAs. `-0 + +0` can change the sign at RNE, so a terminal
   padded result is not automatically equivalent. Original per-step selected
   finiteness checks and faults also cannot silently disappear.
3. MatrixPipeline has8 metadata slots and2 wide results. A held result/capture
   must reserve real credit; no unbounded result snapshots or five captures.
4. K/V preload and normalized P must be committed and valid before consumption.
   Lease/generation/abort/reset/ACK behavior needs a real interface model.
5. One-owner QK/softmax preparation and PV overlap need explicit independent
   state/port reservations. This package credits no overlap or pipeline timing.

The isolated capture/credit specification below now covers opaque transaction
behavior. The next numerical gate still needs tiny causal rows compared against
the original PV32 FMA chain, including signed zero, cancellation, subnormals,
overflow and original per-step fault behavior. Only then consider frozen-input
numerical work. Do not repeat the rejected wideQK path or launch a full block
from this result.

The simpler complementary optimization is a same-resource K/V cache: current
PV32 source rereads102236160B for Attention; reading Q once and both K/V once
would be1048576B external input bytes for M128, before metadata. That requires
a real bank lease and local port schedule and leaves Matrix issue geometry
unchanged. Probability normalization can also be reused after its first
computation, but fault and publication ordering must be checked.

## Added causal capture and credit specification

`capture_model.py` is an independent proposed interface specification, not an
adapter around the current owner. `test_capture_model.py` drives it with opaque
integer-labelled 16-KiB return bytes. These labels verify which returning key
and row were copied; they do not represent floating-point inputs or outputs.
In particular, there is no BF16 output conversion or numerical fault oracle.

The fixed contracts are:

- Five context leases per group, one committed KV head, eight metadata slots,
  two wide result entries, one 16-KiB capture, one outstanding 64-byte write.
- A context remains busy until its real accepted return. A full result FIFO
  backpressures an emitted return without popping metadata or releasing the
  context. Non-emitted returns consume no result slot.
- Full `(epoch, group, context, cohort, key, last, row-final mask)` identity is
  checked against FIFO-head metadata. Return order and captured rows come from
  accepted metadata, not the current input key.
- The shared capture is occupied by one row-final batch from one emitted
  return. Each selected row is written in eight 64-byte beats and its ACKs are
  awaited before release. It never waits for all 32 rows of that cohort: doing
  so could deadlock an interleaved cohort behind the result FIFO head.
- MatrixDone can precede remaining output ACKs, but a successful group terminal
  requires every row's ACK, an empty capture/FIFOs and no outstanding write.
  Backend completion status and sticky owner/writeback status are independent:
  the sole matching completion is consumed even if only one side has failed.
  A backend error can close an interrupted group after accepted work drains.
  A completion holder uses status-aware `can_accept_done(error=...)`;
  `done_ready` is only a successful-completion convenience predicate.
- Stale/malformed ACKs do not erase the accepted write obligation. Abort/reset
  stops new work and drains accepted returns, buffered results and the matching
  real write ACK. Error terminal locks admission. A later coordinated-reset
  indication is an external precondition, not proof of an actual backend reset.

The conservative event model reaches at most five live metadata entries because
it waits for each context's return before reissue. The actual storage capacity
of eight is independently overflow-tested. Same-edge return/reissue, cycle
latency, bank timing, synchronous-read reservation, SRAM loading, physical
source interfaces and numerical checks are outside this specification.

The deterministic M128 opaque replay covers 10 groups, 3216 accepted
issues/returns, 288 emitted wide snapshots, 1536 causal row captures, 12288
write ACKs and 786432 acknowledged bytes. It includes deterministic randomized
backpressure. These are behavioral events, not a complete numeric model run,
hardware cycles, or an RTL protocol pass. The original 9 geometry tests and
24 new behavior tests pass in both ordinary Python and `python -O`. Independent
review found and corrected a completion-status conflation that could require
replaying a one-shot backend error; dedicated tests preserve that counterexample.

## Reproduce without heavy jobs

From repository root:

    PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s candidates/qwen2_pv_gqa_schedule_screen -p 'test_*.py' -v
    PYTHONDONTWRITEBYTECODE=1 python -O -m unittest discover -s candidates/qwen2_pv_gqa_schedule_screen -p 'test_*.py' -v
    PYTHONDONTWRITEBYTECODE=1 python candidates/qwen2_pv_gqa_schedule_screen/model.py

The printed report includes current source hashes. They identify what was read;
they do not retroactively bind older numerical receipts or constitute fixed
expected-source admission. Existing source files are read only.
