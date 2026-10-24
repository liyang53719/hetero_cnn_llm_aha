# Strict chunk64 contraction model

Isolated software candidate for phase 5 UtMatmul (KB × KT) and phase 6
IntraMatmul (Q × KT), followed by pair multiplication. It does not modify or
select the existing ChunkOwner policy, and is not a complete prefill block.

The numerical contract follows candidates/qwen35_gdn_prefill/chunk/model.py
_matmul and the phase/shape definitions in
candidates/qwen35_chunk_contract/source/GdnChunkAddressPlan.scala:
64 × 128 by 128 × 64, accumulator initially +0, ascending K, separately rounded
FP32 Mul then Add, and a final separately rounded pair multiplication. No
causal zero short-circuit skips the contraction. Fatal flags mask is 30,
matching the isolated StrictFp32MatrixLane proposal; exact subnormals and NX
alone remain accepted.

The integer lane model supplies executable numerical semantics. Tests compare
every intermediate product and accumulator with separate NumPy float32
operations (not BLAS), and twelve complete 128-term chains with the independent
Fraction/RNE reference. The Fraction checks compare each of the 128 rounded
products and accumulators, including their exact flags, before applying the
pair factor; their final pair results and flags are checked too. All twelve
selected pair factors are nonzero. The full-plane NumPy comparison checks
result bits, not an independent full-plane exception-flag oracle.

The M128 fixture uses strictly-upper zeros and exact diagonal ones, matching
the upstream `row - col + 1` causal extent and exp(cum-cum) diagonal. Lower
triangle factors are synthetic random values, not a claim to have executed
the upstream cumulative-decay producer. Inputs have full FP32 mantissa bits;
these are not pretrained weights or upstream model outputs.

## Scheduling and storage

Each K broadcasts 64 A and 64 B words into one conceptual 4096-lane plane.
Mul and Add reuse the same lanes serially; the strict pair costs 8192 lane
passes, not 4096 single-pass FMAs. The 16-lane Vector is used only after all
128 reduction steps. Phases/chunks execute serially. This is logical work
accounting, not issue cycles, physical broadcast routing, actual utilization,
frequency, area, or evidence that existing RTL supports this route.

Two explicitly proposed 4096-word data banks and two 1024-word panels cost
40960 bytes. They are new storage requirements to reconcile with the hardware
budget, not existing/free tensor SRAM. This number excludes control/flags,
Python diagnostic allocations and external addressed input/output storage; it
is not a complete owner resource estimate. The two banks swap after Add;
there is no third architectural accumulator bank. Each phase reads 1280
64-byte beats and writes 256 beats. The interfaces are synchronous modeled
reads/write completions, not asynchronous transport or real ACK evidence.

One Contraction instance now retains exactly the same two bank lists and two
panel lists across calls. Each accepted run clears its accumulator to +0,
fully loads both panels before the next sixteen K steps, and overwrites the
product bank before reading it for Add. A synchronous re-entry guard rejects
recursive submissions from read, arithmetic-observer, and write callbacks
without changing the active counters or workspace. This is not a thread lock.

The two-chunk test reuses this single instance for phase 5 then 6 of each chunk.
The test-only schedule_probe.py observes actual memory calls and arithmetic
list identities, independently deriving addresses from row-major geometry.
It verifies all 8192 ordered events across those four calls: 5120 successful
reads, 2048 arithmetic observations, and 1024 successful writes. It checks
stable bank/panel identity, full panel contents at every reload, alternate
product-bank ownership, and the untouched previous accumulator at every Mul.
These assertions augment, not replace, the existing complete numerical oracle.

New negative tests inject wrong read addressing and copied diagnostic planes
to check that the oracle rejects them; these are monitor tests, not hardware
fault results. Actual model tests reject nested work from all three callback
types and stop on a short/nonfinite beat during the second panel load. The
failed beat does not install data or increment completed reads, no K=16 work
or output write occurs, and a following real run reuses the same workspace
without stale partial-panel/accumulator data. Failure never rolls back or
publishes external writes; the older arithmetic/partial-write tests remain.

Source-grounded limit: upstream chunk/model.py _matmul traverses output row
and 16-column beats before K and yields memory transactions. This candidate
instead proposes whole-plane two-pass reuse and synchronous callbacks. It
does not reuse or validate that existing owner's scheduler/transport. The
caller still chooses phase/chunk order. There are no outstanding reads,
stalls, delayed/duplicate ACKs, abort/drain, publication or state-carry models
here; the proposed storage is not evidence of physical bank ports or timing.

The M128 test executes two distinct complete chunk64 contractions for both
phases at one head: 2,097,152 strict MACs, 4,194,304 Matrix lane passes and
16,384 Vector lane operations. It checks 4,210,688 intermediate/output words.
No M1 recurrence, duplicate rows/chunks, padding-only replacement, or sampled
output is used. It does not execute all 16 heads, phases 1–4/7–18, triangular
solves, recurrent state carry, gated normalization, projections, a full block,
or hardware. Inputs are supplied at the phase boundary, not fabricated as
successful outputs of those missing phases.

## Run

From repository root:

    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 timeout 60s bash -c 'ulimit -v 524288; ulimit -t 60; taskset -c $(awk "/Cpus_allowed_list/{split(\$2,a,\",\");split(a[1],b,\"-\"); print b[1]}" /proc/self/status) python -B -m unittest candidates.qwen35_chunk_strict_contraction.test_model -v'

This bounds virtual address space to 512 MiB and execution to one permitted
CPU. The 60-second wall-clock and CPU limits cover the complete test process.

VALIDATION_SCOPE.json is preserved as the original seven-test numerical receipt
for commit a21686c52a7f60f728165950c78a73b789193a6d, not a manifest of the
extended files. SCHEDULE_VALIDATION_SCOPE.json records the historical ten-test run
and source hashes at that revision. Historical timings do not qualify changed code.

Requires already-installed NumPy. No download, compilation, hardware job, or
production/source manifest changes. An adversarial full Contraction run checks actual output/intermediates against
independent Fraction arithmetic and demonstrates that FMA fusion, reversed K
and factor-inside-reduction alternatives disagree with its output. This is
not just a standalone scalar arithmetic demonstration. It also checks NX,
exact subnormals and signed-zero product/add behavior. Fault cases exercise
MulFatal overflow before Add, AddFatal overflow, pair underflow after one
successful modeled write, and a failing second write. The latter two preserve
the first beat but raise instead of returning successful completion, and do
not count or mutate the failed beat. The pair-fault fixture intentionally
supplies a non-upstream/noncausal factor matrix to reach that generic fault
path; it is not upstream workload evidence. Geometry controls reject M1 and
aliased spans. No asynchronous transport, retirement, abort/drain or publication
protocol is tested. This remains software-only regardless of test outcome.

## Actual upstream coroutine replay (separate integration boundary)

upstream_coroutine.py now binds the existing ChunkOwner._matmul, _read,
_write and _mul_add executable methods directly, rather than copying their
control flow. Only _op is replaced by the same strict integer FP32 primitive
used in Contraction. It therefore executes the ORIGINAL row/16-column-beat/K
memory schedule, NOT the proposed whole-plane two-bank/panel schedule.
No ChunkOwner policy or production source is changed, no Vector16 binary is
loaded, and no native Vector16 numerical equivalence is implied. In particular,
the known minnormal boundary is strict flags=3 and stops before Add; the old
Vector16 C++ flags=1 discrepancy remains an integration blocker.

The bounded adapter exposes the existing MemoryRequest/MemoryResponse types
and resumes the actual upstream coroutine only after a valid matching full
64-byte response. The test uses the existing TypedMemory begin_write,
write_data and acknowledge methods. Request suspension is a Python generator
boundary, not ready/valid clock timing. The caller owns physical completion
and drain. Closing the adapter releases only its local ownership, never a
physical accepted transaction. There is no ChunkJob admission, ChunkResult,
TypedChunkDriver, full owner abort/reset/drain, or output/state publication.

The new test executes one complete phase 5 and one distinct complete phase 6,
at one head and one chunk boundary each. It compares all 2,105,344 intermediate
and output words AND flags against the whole-plane strict model, and checks
all 70,656 requests against independently derived row-major addresses/tags.
This cross-schedule comparison shares the integer arithmetic primitive; it
is not an independent full-plane flags oracle. The original NumPy/Fraction
tests remain the independent numerical evidence. Inputs are fresh synthetic
phase-boundary matrices, not upstream prep/decay output or a full M128 chain.

Each replay phase performs 35,072 reads and 256 writes, versus 1,280 reads and
256 writes in the proposed panel schedule. These actual software transaction
counts expose the unresolved scheduling/storage tradeoff; they are not cycles,
hardware bandwidth, utilization or QoR. All output bytes become written and
ACKed but remain unpublished. Negative tests reject malformed/stale responses,
nonfinite input, and re-entry while a write is suspended; a bad second ACK
leaves only the first beat acknowledged and never publishes the destination.
The test explicitly retires the physical failed write itself, not the adapter.

Run both numerical/schedule and upstream-replay suites within the same bounds:

    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 timeout 60s bash -c 'ulimit -v 524288; ulimit -t 60; taskset -c $(awk "/Cpus_allowed_list/{split(\$2,a,\",\");split(a[1],b,\"-\"); print b[1]}" /proc/self/status) python -B -m unittest candidates.qwen35_chunk_strict_contraction.test_model candidates.qwen35_chunk_strict_contraction.test_upstream_coroutine -v'

UPSTREAM_COROUTINE_VALIDATION_SCOPE.json records this revision's bounded run.
Earlier validation receipts remain historical and do not qualify changed code.
Next integration requires an explicit phase hook in the existing owner and
the same TypedChunkDriver allocation/ACK/drain obligations, full producer
provenance, and output/state staging. Moving the whole-plane program there
also requires actual suspended-read/write workspace lifetime, resource leases,
fault drain, and physical bank-port/broadcast accounting. This replay does not
resolve those requirements or validate phases 1–4/7–18, state carry, full block
or RTL.

## Injected phase on the actual owner/typed-driver lifecycle

injected_owner_phase.py is a deliberately test-only, instance-local hook, not
an enabled production policy. It uses an actual ChunkOwner and unchanged
TypedChunkDriver. Their original tick, ports, admission, leases, request
identity, scratch byte writes/ACKs, response validation, abort/reset drain,
terminal holding and retirement methods execute. The original row/beat/K
_matmul, _read, _write and _mul_add execute with explicitly injected strict
integer-software _op. No copied lifecycle controller is introduced.

The fixture admits a one-head, 64-token, K128/value128 ChunkJob but replaces
_compute with ONE phase. A synthetic admission-only input span is physically
written, ACKed and published by the fixture, not produced by Prep arithmetic.
Three synthetic phase operands are then written into the real ScratchPlan by
1,280 actual driver write/ACK transactions before that same driver permits
scratch reads. This proves transport provenance only, NOT numerical producer
provenance. The actual phases 1–4/7–18, original _compute, complete producer
chain, state carry and complete ChunkJob remain unimplemented in this hook.

As in the upstream TransportOnlyTests, Vector16 is a noncomputing lease shell
with original acquire/release methods. No Vector16 library is loaded; native
operation counters remain zero. The unchanged owner acquires/releases that
shell and a real PrepScalar; strict-software operation counts stay separate.
Strict ArithmeticFault is explicitly translated to the owner's ArithmeticFault
so its real Numerical terminal path captures phase/K/result/flags. This does
not fix or qualify the native Vector16 minnormal flags discrepancy. Raw
owner source_identity/report fields describe the original owner code only;
they must not be used as numerical provenance for this injected program.

Both full UT and QK contractions execute through this path and compare every
final word against independent NumPy float32 Mul then Add, followed by pair
Mul. The earlier full-intermediate and Fraction suites remain separate
numerical evidence. Per phase, the actual driver performs 35,072 reads and
1,536 writes/ACKs (1,280 fixture writes plus 256 contraction writes). Counts are
software transactions, never hardware cycles, bandwidth or utilization.

CRITICAL: even after all 256 contraction writes are ACKed, the original owner
returns Protocol, not success, because no job.output/state_out bytes were
written. That expected failure is the test's no-false-completion assertion,
not a completed ChunkJob. Result.staging_complete, all publication/commit
flags and generation advance remain false. The output/state allocations stay
untouched. Exhaustion of an isolated injected phase cannot pass the original
owner's full write-byte or typed-driver whole-staging gates.

Tests hold the last ACK, block request acceptance, suspend accepted reads and
writes, and inject abort/reset while preserving real leases until drain.
Stale/duplicate ACKs, malformed byte counts/error types, Memory errors,
nonfinite reads and strict flags=3 underflow exercise the existing owner
terminal paths without granting bad-ACK credit. Partial scratch writes stay
unpublished. detach removes the two test hooks only after drain and terminal
retirement; calling it earlier is rejected. Reset then restores normal ready
state with original _compute/_op, but does not qualify a subsequent full job.

Run the existing suites plus this lifecycle regression under the same bounds:

    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 timeout 60s bash -c 'ulimit -v 524288; ulimit -t 60; taskset -c $(awk "/Cpus_allowed_list/{split(\$2,a,\",\");split(a[1],b,\"-\"); print b[1]}" /proc/self/status) python -B -m unittest candidates.qwen35_chunk_strict_contraction.test_model candidates.qwen35_chunk_strict_contraction.test_upstream_coroutine candidates.qwen35_chunk_strict_contraction.test_injected_owner_phase -v'

INJECTED_OWNER_VALIDATION_SCOPE.json records the bounded run separately from
historical receipts. No production owner source or class policy is modified.
This is real software lifecycle coverage with explicitly injected arithmetic
and operands, not full-owner integration, full-block acceptance, or RTL proof.
