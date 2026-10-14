# Bounded fresh M128 pc0..12 preparation

Status: NOT_EXECUTED. This package does not claim numerical acceptance. A new
independent parent review and explicit go for its current closure are required.
The parent alone starts the one fresh actual run. Historical approval bits,
169/188/194-file results, and other candidates cannot grant permission or PASS.

## Minimal change and provenance

- All original 169 M128 sources are frozen byte-for-byte in pins.json. The old
  M128 and M16 source trees are read-only; DenseIdleV1 is not used.
- runner.py is the old M128 runner with bounded admission, timing, native-code
  reuse, telemetry, and failure receipts. Original arithmetic, all require gates,
  physical memory, Host, Matrix, Scalar, original PV32 owner/observer, comparison
  policy, full causal coverage, and final pc12 held boundary remain unchanged.
- attention_driver.py copies the original execute_attention_owner. Its sole
  control addition samples after every 131072 completed driver loop iterations.
  Removing the new progress argument and that unique if restores the original
  function AST exactly. There are no model or observer monkeypatches.
- Telemetry reads actual existing counters, accepted requests/results, ACK bytes,
  owner states, public state, output publication, resource debts, and peak RSS.
  It does not tick, publish, calculate substitute counters, or write model state.
  Stage records cover prefix and setup; long Attention progress is sampled at
  completed loop boundaries. Samples are diagnostics, never acceptance evidence.
- SIGALRM only throws at the absolute 900-second entry deadline; it never reads
  model fields. Failure capture occurs after unwinding and retains the original
  exception type/message and traceback. Known budget errors are chained with a
  stage-specific wrapper using the original exception as __cause__.

## Native code only

No compilation occurs in this entry. It verifies and reuses exactly these old
read-only native code artifacts:

- work/qwen2_live_attention_numeric_m128_20261014/m128_pv32_actual_v1/build/official_bf16_compile.json
- work/qwen2_live_attention_numeric_m128_20261014/m128_pv32_actual_v1/build/official_bf16_matrix_silu.so

The receipt digest, ELF digest, all strict compiler flags/translation units,
source hashes, and current compiler hash/version are rechecked through the
unchanged original verifier. Hashes are rechecked after the run. ctypes.dlopen
can target only that exact pinned ELF. Old-run reads can reach only the receipt
and ELF, read-only; all old QKV/output data remains forbidden. The entry records
native_artifact_reuse separately and never labels it a fresh compilation.

This is native C++ Matrix/SILU code, not Scala, HostBlockTop, Verilator, RTL, or
EDA. Removing a build cannot be claimed as an arithmetic speedup. The new
process performs the original td_reset and builds entirely fresh model state.

## Input, seal, and acceptance

The existing raw recipe is validated and exactly nine inputs are freshly loaded:
x, gamma0, wq, wk, wv, bq, bk, bv, rope. No saved QKV or partial run is an input.
All pc0..12 work shares one execution, PhysicalMemory, Host, Matrix, and Scalar.
KV append requires live K+V exact-copy and full ACK coverage. Attention must
complete its entire causal schedule, including 1188864 actual Matrix requests
and results, 608698368 executed normal FMAs, and 25362432 useful FMAs.

The original output ACK/terminal/debt checks, five held-boundary edges, same-live
identity check, pristine suffix, and observed tensor writes precede the actual
output seal. Only then may the original eighteen-node reference payloads open.
No numeric thresholds are changed. Raw qraw/kraw/vraw have no invented official
reference. att stays unpublished, pc12 completion stays held, and fullblock,
whole-block terminal, typed bit-exact hardware acceptance, and RTL claims remain
false. This is still the eighteen-node Attention-reference scope; the separate
29-node complete-block reference project is not imported or inherited.

On any error, acceptance_sealed is false. A pre-seal timeout also leaves
actual_outputs_sealed false and oracle closed. A post-seal failure truthfully
retains the earlier physical seal as history but never acceptance. The outer
supervisor cannot promote a timed-out child report to PASS.

## Budget and uncertainty

The old failed M128 run reached KvAppend at 77.861710 seconds and then spent
492.228940 seconds executing 921633 of 1188864 Attention steps (77.5221556%).
Linear extrapolation gives 634.9526 Attention seconds and 712.8143 total seconds
through Attention. A 25% allowance is 891.0179 seconds, before any unmeasured
post-terminal seal/comparison/final-hash cost. This is a planning estimate, not
a completion guarantee or a measured new-entry speedup.

The single shared inner deadline is 900 seconds from run admission, including
closure checks, input hashes/loading, native-artifact/tool validation, setup,
all execution, snapshots, output/seal, oracle comparison, final hashes, and
receipt write. The following planning allocations total 900 seconds; they are
not separate stage timers and unused time remains available to later stages:

- 15 s: dependency/source/input hashes, pinned native code and tool verification,
  nine-input loading, fresh model/physical-map setup
- 100 s: pc0..8 producers, held boundary, and live pc9 KV copy/ACK
- 750 s: complete unchanged causal Attention, including sparse read-only telemetry
- 10 s: observation/output writeback, pc12 held checks, suffix/debts, physical seal
- 10 s: post-seal eighteen-reference reads and unchanged official numerical gates
- 15 s: final source/input/raw/reference/tool hashes and final receipt write

These suballocations are intentionally advisory and not individually measured.
The prior 77.861710 seconds combined its own setup and prefix cost, so it cannot
establish separate setup/prefix ceilings. Attention runtime is extrapolated from
accepted progress, not guaranteed linear: remaining row lengths, CPU scheduling,
observer work, memory pressure, and telemetry overhead may change it. A uniform
25% slowdown alone consumes about 891 seconds and leaves only about 9 seconds
for unmeasured tail work. Thus 900 seconds is a bounded experiment, not a promise
of 25% end-to-end headroom. Native build reuse has no claimed arithmetic benefit.

The supervisor's absolute 930-second deadline starts before its own preflight
hashes. Child wait deducts elapsed setup and normal exit is rechecked against the
deadline. It runs an isolated process group. Cleanup is INCLUDED in the 930
seconds: execution cutoff/group TERM is at 924 seconds, group KILL no later than
927 seconds, reaping stops by 929 seconds, and one second is reserved for the
final supervisor receipt. All waits deduct elapsed time; no wait is unbounded.
If the OS cannot reap by the bounded cleanup deadline, cleanup_incomplete is
reported and acceptance remains false. Process scheduling and filesystem stalls
can delay receipt visibility; they cannot extend an authorized child wait. Child RLIMIT_AS remains 2 GiB and
OMP/OPENBLAS/MKL thread counts are fixed to 1, as in the original run.

## Cold tests and admission

Use python -B -m unittest candidates.qwen2_live_attention_model_m128_bounded.test_cold.
Run both normal Python and python -O; actual observation still requires the
original CPython 3.12 nonoptimized runtime. Cold tests use only hashes, source
ASTs, synthetic control objects, and mock failure/supervision paths. They never
import the numeric runtime, load .so, execute inputs, or compile.

Required review checklist:

1. Original 169 source digests unchanged; new closure and pin hashes exact.
2. Driver AST equivalence after deleting only the specified telemetry addition.
3. All original numerical/physical require gates preserved; only historical
   approval and default CLI gate are superseded by stricter new admission.
4. Snapshot mutation test, original exception-cause preservation, 900 deadline,
   exact native read/dlopen tests, early oracle denial, and bounded group cleanup.
5. New default CLI returns NOT_EXECUTED; old approval bit cannot enable a run.
6. Exact approved current manifest supplied to the one supervisor invocation.
7. Output directory absent; no sessions resume, no saved QKV, no threshold edits.

The one proposed output is:
work/qwen2_live_attention_numeric_m128_bounded_20261014/m128_pv32_bounded_actual_v1

Only after independent parent go, invoke launch.py with --actual, the current
--reviewed-source-manifest, --data work/qwen2_live_qkv_inputs_m128/frozen01,
--reference work/qwen2_live_attention_reference_m128/frozen01/reference, and the
above --out. The supervisor writes sibling .LAUNCH.json/.stdout.log/.stderr.log;
the child writes RESULT.json, PROGRESS.jsonl, and fresh outputs inside the run.
The exact command and closure identity are recorded in FREEZE.json. Neither this
README nor FREEZE.json grants execution permission. No stage/push is performed
by this preparation task.
