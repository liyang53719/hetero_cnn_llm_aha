# Fresh same-live M128 public21 full block

Status: implemented for source/cold-control review only. No complete numeric run,
no timing trace, no compile, no Torch, no RTL and no publication are performed by
this package's default entry. `BUDGET.json` deliberately contains no execution
budget and refuses `--actual`, even with a matching source manifest.

## Narrow continuation

The new runner retains the unchanged v2 fresh pc0..12 sequence. It installs all
14 pinned readonly inputs and one original `FullGraphMemory` before launch. At
the actual held pc12 it retains the identical Attention job, releases completion
12, then executes the original pc13..20 tail. The cold AST test compares that
body to `ffn_public/fullgraph_execution.py` after removing only read-only stage
annotations and the historical acceptance label. No owner, arithmetic, packet,
profile, descriptor, threshold or old source is changed.

The same five-context Matrix resource, three resident tile slots, A/B SRAMs,
ScalarService and 786432-byte workspace persist. O has no prefix transport;
Down retains K chunks 2560/2560/2560/1280, 144 seed ACKs, and three full physical
prefix write/read rounds. Gate/Up are observed only from real resident tile
reads; physical Gate/Up DDR remains pristine. All continuation operands come
from actual acknowledged and publicly published storage. Saved pc12 output
cannot be loaded, restored or resumed through this runner.

The selected original `sf_vector_bf16_v1` is reset exactly once and wrapped by
the original `ObservedSiluLibrary`. FFN's existing vector ABI/coordinator is not
proof of a unified physical arbiter with ScalarService; that hardware claim is
explicitly false/unproven in the report.

Only actual 21 completions, 17 owner jobs, one accepted final launch result,
unchanged live identities, complete outputs and drained obligations permit the
oracle to open. `finalfence` describes this software public termination; there
is no extra fence opcode or RTL execution. The reference is the fresh frozen29
original-AST capture, not full Transformers forward or DynamicCache execution.
Original BF16 operator gates and final-y block gates remain unchanged.
`softmax_fp32` has no approved elementwise tolerance. Missing raw Q/K/V official
references and absent future-mask observations remain explicit.

## Read-only counters

`statistics.py` takes stage-boundary snapshots only. Consecutive stage intervals
cover every observed Host edge with no overlap/gap and state exactly where
public decode, completion holds and launch-result holds are included. This is
not a canonical per-edge busy census. Issue accepted, leases acquired/released,
actual C FMA calls, memory/ACK/seed counters and Scalar/SiLU calls remain distinct.
No service methods or model counters are replaced or written.

Full-array issued opportunities use 4096 times accepted Dense+normal steps.
Five contexts and three tile slots are storage, not independent issue engines.
Actual executed/useful FMA and issued-cell opportunities are separate fields.
Hardware cycles, hardware utilization, hardware busy fraction, absent software
busy/ownership counts, and model issue/ownership fractions remain null.

Success schedule predictions (checked against actual counters only after a run):
- Whole: 2651136 accepted wide steps; 10859053056 full-array issued opportunities
- Actual C FMA: 6598164480; useful Matrix FMA: 6014828544
- Tail: 1363968 Dense steps; 5586812928 C FMA; 162 groups; 800 results; 114 leases
- SiLU: 71680 original 16-lane vector calls; these are not hardware cycles

## Budget prerequisite and minimal timing proposal

The immutable v2 stage receipts show approximately 80.5 seconds for pc0..9 and
669.3 seconds for Attention, reaching held pc12 in about 753 seconds. The Q
projection's 73728 accepted steps took about 39.7 seconds, but its QKV partial
profile differs from O/FFN/Down. It is not a safe whole-tail upper bound. The old
900/930-second budget does not authorize or bound a complete block.

Before filling `BUDGET.json`, review a separate one-use, cost-only trace with an
explicit short wall/RSS/disk cap and the same ELF, original owner/Matrix adapter,
4096-cell width, five contexts, three slots and M128 geometry:
1. One complete original O projection (73728 steps, 10 groups, 48 results),
   including genuine memory/ACK/lease work. If it uses archived att, label every
   receipt `ISOLATED_COST_REPLAY_NOT_SAME_CHAIN`; no numeric/fullblock verdict.
2. One complete original Gate/Up/SiLU/drain window (15360 Dense steps, 10
   results, 1280 vector calls) with real retained-A/tile handshakes. A separate
   cost harness may use original partial-window test control, and must report
   an unfinished public group rather than manufacture completion16..18.
3. Down needs an original-driver trace reaching at least the first complete
   2560-K sweep and a following genuine prefix read/seed ACK. A bounded deadline
   stop is an intentionally incomplete cost trace with retained debts, never a
   successful Down/fullblock run. Do not substitute synthetic seed acknowledgments.

The trace harness itself still needs independent source review. It is not
implemented or executable through this fullblock entry. Required measurements
are wall/CPU seconds per accepted Dense step, memory/seed counters, native FMA
deltas, output bytes, peak RSS, and fixed setup/SiLU/ACK overhead. Full-run
budgeting must reserve all 56 FFN windows, all four Down chunks, complete output
sealing, source/input/reference rehash, original-policy comparison and process
cleanup, with a justified safety margin. M16 does not reduce tail step/FMA work
and is not a cheaper substitute. If the short trace cannot observe the required
phase before its approved cap, preserve that result and return for review.

## Cold checks

Run from repository root (normal and `-O`):

    python -B -m unittest candidates.qwen2_live_fullblock_model_m128.test_gate_cold candidates.qwen2_live_fullblock_model_m128.test_cold -v
    python -B -O -m unittest candidates.qwen2_live_fullblock_model_m128.test_gate_cold candidates.qwen2_live_fullblock_model_m128.test_cold -v

The initialized probe loads the exact native code and constructs real services,
physical memory, workspace and public Host. It only decodes metadata to offer
pc0; no owner request fires, input/reference payload is read, Dense FMA occurs,
SiLU vector executes, or Scalar service operation is called. The original
Scalar constructor's five environment probes run. Postseal permission testing
uses a separate uninstalled gate while the installed gate remains closed.
This catches real import, native/FENV, metadata, scratch-cleanup and source-path
self-locks that fake service doubles would miss.

## Proposed command, after review only

First source-review a fixed whole-scope `BUDGET.json`, then review the resulting
exact source manifest and authorize one fresh output name. There is no CLI
budget override and no automatic retry. Only then the parent may run:

    python -B candidates/qwen2_live_fullblock_model_m128/launch.py --actual --data work/qwen2_live_qkv_inputs_m128/frozen01 --reference work/qwen2_fullblock_reference_capture_20261014/fullblock_pair_v2/frozen --out work/qwen2_live_fullblock_numeric_m128_20261014/parent_reviewed_fresh_v1 --reviewed-source-manifest REVIEWED_MANIFEST_SHA256

The supervisor has an outer deadline, bounded TERM/KILL/reap, sampled process
RSS/output/log caps, and child address-space/per-file limits. Sampled aggregate
caps can overshoot between polls and are not represented as OS hard RSS/disk
limits. Failed receipts/output and outstanding simulated debts are retained. Process-group
cleanup does not execute or prove backend abort/drain; zero backend debt is required
only on the successful terminal path. No raw, array, ELF, checkpoint,
or old acceptance state belongs in Git.
