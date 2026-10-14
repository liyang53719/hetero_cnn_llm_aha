# Dense idle specialization V1

This is an explicit new-scope software experiment. Existing Dense, Tile, Host,
public execution, observer, Matrix/Scalar/C sources and their defaults are
unchanged. It does not authorize M128 or establish an architecture speedup.

## Candidate and proof domain

`DenseIdleOwnerV1` accepts only an argument-free `tick()` on the exact new class
with original construction-time Tile/A/B identities, source-bound inherited
ports and helper descriptors, original arbiter/bank descriptors, all five flags
exactly true, clean idle state and no owner/tile/window/drain/DMA/Matrix/seed
obligation. A newly added override, changed method code, foreign class, swapped
bank, explicit default keyword or malformed/missing required field falls back.
The original inherited tick is called once with untouched arguments. Python's
own argument binder and original exceptions remain authoritative. No exception
is caught or rewritten by the candidate.

On eligible states, K-window routes to drain, drain routes to window, and window
selects its clean idle tile edge. Their two pure pre-edge ports snapshots are
identical. V1 takes one dynamic original `ports()` snapshot, calls the original
Tile arbiter with exactly the effective original idle arguments, retains the
original lease-invalidating condition, increments the owner clock once and
constructs the same event in the same key order. No event key is filled merely
because it is absent. A-bank cycle dictionaries are replaced by the original
arbiter; B-bank bookkeeping retains its identities and contents. Returned A
access dictionaries alias the actual Tile event dictionaries. Output B access
dictionaries and the top-level event are fresh.

Historical job, nonzero integer counters, sequence metadata, SRAM words and
released tag metadata remain unchanged. A completed ordinary job's retained
write descriptor deliberately prevents the V1 fast route. A real completed
Dense drain does regain eligibility. The conservative rule is not relaxed to
improve hit rate. Diagnostics and construction identities live in an external
weak-key mapping, not the owner or architectural counters.

The proof domain is exact source-bound classes and typed reachable model state,
not arbitrary hostile Python metaprogramming. Descriptor/code identity fences
cover the call chains whose purity permits deleting the duplicate snapshot.
The source closure is checked before/after the actual probe.

## Cold gate

Run `python3 -B -m candidates.qwen2_attention_idle_fastpath.test_owner`.
The suite uses real original control classes and TileBank, complete recursive
state/event/type/key-order/alias comparisons after every edge, and an external
cold profiler to verify original fallback/ports/Tile call entries. Opaque finite
wire tokens exercise transport; no arithmetic library is loaded or compiled.
Legacy imports may use installed numeric packages, so this is not a claim that
imports are stdlib-only. Actual ordinary/window/tile/drain/reset/relaunch paths
are exercised. Cold fault injections affect instances or only the new class,
never an existing class or source. Exceptions normalize only the explicit old
versus new root-class spelling in Python-generated AttributeError messages.

`test_probe.py` checks exact constructor deltas, inherited method identities,
manifest/tool gates and the external recorder without running arithmetic.

## Proposed bounded synthetic A/B

Only after independent source/guard/alias review, a manifest with status
`REVIEWED_SOURCE_ONLY_FOR_M2_RECORDED_M8_ABBA` enables the explicit `--actual-budget`
runner. The default invocation performs no numeric work. The supervisor permits
at most 45 seconds, one pinned CPU, CPython3.12 and OMP/MKL/OpenBLAS threads=1.
An existing source-verified original BF16 ELF/compile receipt is reused by exact
identity; every isolated child starts fresh and resets its own C state. No
previous model output or observation is reused as an operand.

Two observed, fully recorded old/new public3 M2 conditions compare every
actual Attention/Host edge, accepted inputs, counters, actual clock increments,
full relevant public/control state, raw output, physical ACKs, trace and all
observation buffers. A separate read-only `sys.monitoring.PY_RETURN` recorder
captures the actual Dense event discarded by the unchanged public method. It
uses its own tool ID, exact source code/frame/owner/thread checks, and cleanup
that preserves unrelated registrations. It does not alter PV32 observation.
Each public boundary consumes exactly one genuine Dense return.

Per-edge complete control/Counter/key/alias state is factored from unchanged
SRAM values. The recorder captures all initial bank words, checks stable bank,
word-array and row identities plus actual empty Dense/Tile A/B access events
and source-bound debt-free idle state each edge, then compares every final
word with the baseline. Per-edge word-array references are a source-derived
unchanged-state invariant, not freshly observed per-edge memory hashes. No
cached fabricated event or modeled counter replaces actual execution.

Four separate unrecorded observed M8 conditions run in balanced
old/new/new/old order and record wall/CPU separately. M2 and M8 fixture,
stimulus, observer coverage and actual-work identities are pinned and compared
within their own scope, never falsely cross-compared as identical work.
No observer-off arm is required for this bounded experiment. The existing registered PV32 observation
callbacks, source methods, owner instance methods and Host-tail path are unchanged.
Recorder cost is isolated from timing, never subtracted as an estimated amount.

M8 actual counters must assert 44,036 driver ticks, 44,037 Host/Dense/Tile edges,
7,680 accepted reads, 768 accepted ACKs, 5,184 normal steps and 2,654,208 C FMA
calls. M2 work counts are also read from actual execution, with its complete
12-head causal coverage checked separately. No work counter is prefilled.
A first mismatch leaves
a first-divergence artifact. The fixed execution/test-source whitelist and old 169/M16 188 source
identities are rechecked. README and later publication metadata are recorded
separately from that execution closure; historical execution receipts and
closed manifests are never rewritten to inherit a result. A rejected gain is a valid result. This synthetic
public3 experiment cannot establish a full public21 or M128 wall budget.


### Why the recorded equivalence scope is M2

A real-control, no-arithmetic cold sample of 1,024 fully recorded edges cost
0.975856 seconds (old) and 0.947452 seconds (new), producing 13,492,144 raw and
649,131 compressed bytes per arm. Extrapolating that recorder alone to two
44,037-edge M8 traces costs about 82.7 seconds before Attention, its observer,
ABBA, setup and finalization. A 25% allowance plus 5 seconds setup/finalization
and the prior roughly 13.2-second ABBA cost puts that rejected plan above
121 seconds. The original cold receipt is retained, never overwritten.

The separately approved plan instead records two complete M2 public3 runs,
then uses four complete M8 public3 runs for performance. At approximately
4,446 admission-inclusive M2 edges, the original cold serializer predicts
about 8.35 seconds of recording cost across both arms. Adding a 25% allowance,
real M2 arithmetic/observer cost, approximately 13.2 seconds M8 ABBA, and
5 seconds setup/finalization yields a planning range of roughly 29–35 seconds.
This is an explicitly uncertain cold-sample prediction, not measured numeric
performance or a guarantee. A hard 45-second bound remains mandatory. Any
later lossless recorder improvement gets its own cold receipt; it does not
turn the rejected full-M8 recording plan into an authorized run.

Final frozen recorder calibration supersedes that initial 29–35 second planning
range. With all agreed identity/alias/debt checks and lossless primitive dispatch,
1,024 real M2-public quiet control edges cost 0.624470 seconds old and 0.670440
seconds new on CPU 0 with all three thread variables set to 1. Both produced
identical 647,798-byte compressed streams (13,492,144 bytes uncompressed).
Allowing 6,000 recorded edges per M2 arm, 4 seconds for active Attention/PV32
observation and packet serialization, the prior 13.2-second M8 ABBA cost and
5 seconds setup/finalization, then applying 25% margin, predicts 37.57 seconds.
This conservative forecast is not a measured numeric bound or a Dense speedup
claim. Exact M2 tick totals are obtained only from the upcoming run. The final
cold receipt is `work/qwen2_attention_idle_fastpath_20261014/recorder_cold_v1/FROZEN_COLD_RECEIPT.json`.
