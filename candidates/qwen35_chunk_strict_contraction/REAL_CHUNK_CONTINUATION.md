# Actual chunk0 completion and bounded chunk1 state carry

This is a separate extension of `REAL_PRODUCER_SLICE.md`. The original
QK-then-abort diagnostic, its 22-test regression, and all historical receipts
are retained unchanged. The new test is
`test_real_chunk_continuation.RealChunkContinuationTests`.

## Executed path, and the stopping boundary

The same raw synthetic BF16 Conv/AB fixture enters the original M128
`InputPrepOwner`/`TypedInputPrepDriver`; all 128 Prep rows are physically
written, ACKed and published. A_log/dt_bias remain readonly raw parameters.
The fixture is not evidence of executed projection, convolution, RMS or a
pretrained checkpoint. One active head retains the full 6400-FP32-word core
stride; the other 15 heads are explicitly zero-written by Prep.

That actual published core enters one cold M128 `ChunkJob`, with heads=1 and
Dk=Dv=128. The original `ChunkOwner._compute`, `_solve`, `_matmul`, `_binary`,
transpose, transport, ACK and lifecycle implementations execute unchanged:

1. Head0/chunk0 executes all producers, UT/QK, both unit-lower solves,
   prediction, value subtraction, inter/local output, state update/decay/add,
   and all 8192 BF16 output elements. Its complete 65536-byte next_state is
   produced in scratch. The final output ACK is held to verify that
   chunks_completed stays zero and leases remain held until the ACK arrives.
2. The actual generator advances to chunk1 of the same M128 job. It loads and
   processes the second 64 distinct Prep rows, restarts cumulative gates from +0,
   completes UT/QK and both solves, and executes the first full prediction
   row: 128 output elements, each with an ascending-K128 reduction.
3. This first chunk1 prediction row reads every one of the 1024 beats of
   chunk0 next_state exactly once through the original driver's ACK-checked
   scratch transport. No externally published state, synthetic state input,
   copied reference operand, per-token recurrence or second M1 job is used.
4. After that prediction row's final ACK, the next row's first solvek read is
   accepted. The test asserts the original abort and holds the response in
   drain with both resource leases still held. Draining does not resume the
   arithmetic generator. A held `Aborted` terminal is retired normally, then
   the existing strict hook is detached and the owner reset.

This stopping boundary was selected before the first bounded attempt. No
timeout, numerical failure or abort was converted into success. This is NOT
full chunk1, full M128 recurrent execution, all-head execution or a full block.
The independently computed full chunk1 prediction reference is NOT a claim
that the actual generator executed more than its first row.

## Arithmetic and independent comparisons

Only the already existing instance-local `StrictProducerArithmetic._op`
hook is used. Strict integer-software FP32 Add/Mul operates on 1..16 active
lanes; fatal mask30 is unchanged. Original PrepScalar Div/Sqrt/Softplus and
ExpNegative recipes remain unchanged. Vector16 is still the noncomputing
lease shell: no native Vector16 library or arithmetic invocation occurs.
The original owner's source identity does not identify this test-only hook;
the separate continuation receipt identifies the tested program.

Expected arrays never enter actual memory. Comparisons include:

- All 819200 Prep words against the existing independent Fraction/RNE oracle.
- All 16384 words of the actual initial cold state against +0.
- All 24 chunk0 matrices, 201728 FP32 words, against independent full arrays.
- Chunk1's 12 producer matrices, UT/QK, both solves, and first prediction
  row, 111744 FP32 words, against independent arrays.
- Every one of 13816128 executed strict Add/Mul intermediate results against
  separate NumPy float32 operations at the same arithmetic node.
- Every one of chunk0's 8192 BF16 output words against an independent
  retained/remainder/tie-even rounding implementation, not the owner's
  rounding-bias formula.

The full-array reference uses ascending K, separately rounded Mul then Add,
+0 accumulators, raw sign-bit negation, and an implicit unit diagonal in the
forward solves. It does not divide by stored UT diagonal, skip masked dot
products, collapse signed zeros, call owner arithmetic helpers, or use BLAS.
Decay arrays use the existing Fraction polynomial-exp oracle, not a new
production transcendental service. This deliberately benign synthetic range
has no saturated or zero exponential output. It is not pretrained accuracy or
exhaustive underflow coverage. Every strict flag is checked to be 0/NX here;
there is no new independent full-plane exception-flags oracle. Prior exact
flags tests and the known native Vector16 minnormal discrepancy are unchanged.

## Accepted requests and retained partial state

The following exact counts are asserted, not merely estimated:

- Chunk reads: 474881. Published Prep source reads: 3200 beats / 204800 B.
  Scratch reads: 471681 beats / 30187584 B, including the final drained read.
- Chunk writes and write ACKs: 20872, comprising 20616 scratch beats and
  256 external output beats. Scratch ACK bytes: 1319424.
- Strict Mul lanes: 6930432. Strict Add lanes: 6885696. Width1 issues: 4416;
  width16 issues: 863232. Original ExpNegative calls: 4418.
- `chunks_started=2`, `chunks_completed=1`; terminal status `Aborted`,
  `write_bytes=16384`, `staging_complete=false`.

The full job's scratch reservation remains 1679360 B. Its unexecuted 359936-B
suffix, the output's second 16384-B half, and all 65536 B of state_out retain
their original allocation bytes. State_out has no writes or ACKs. Output,
state_out and scratch all remain unpublished. No generation, state commit or
history commit advances. The completed chunk0 scratch state is an internal
carry dependency, not a separately committed warm-call state.

All three original storage/transport implementations still execute. This is
Python TypedMemory, not evidence of a physical SRAM layout or bounded local
register payload. No native Vector16, Scala/Chisel, HardFloat simulator, JAR,
RTL, device, cycle, bandwidth, utilization, frequency, area or QoR claim is
made. No runtime dependencies, production files, policies or cache contents
were changed; no network, commit or push was used.

## Bounded verification and artifacts

The first actual attempt passed one diagnostic in 48.582 s, process wall
48.840 s, under one permitted CPU, 512 MiB virtual-address limit, and 60 s
wall/CPU limits. Its log, exit status, timer, source hashes, successful
post-run hash check and exact test-source snapshot are preserved under
`reports/execution/QWEN35_REAL_CHUNK_CONTINUATION_20261023/attempt1.*`.
No failed launch, timeout or numerical failure preceded this attempt.

The final source adds independently derived exact request/operation counts
and pristine suffix checks to that initial successful diagnostic. Final-source
independent validation passed in 47.696 s with peak RSS 75276 KiB. The unchanged
historical 22-test regression separately passed in 40.900 s with peak RSS
87884 KiB. Both runs verified the same CPU/AS/wall/CPU-time limits and captured
unchanged before/after hashes for 36 and 37 explicit files respectively, not
a complete runtime import closure. The reviewer created no log files; the
exact reported results and hash scope are recorded in
`REAL_CHUNK_CONTINUATION_VALIDATION_SCOPE.json`. Do not apply the first run's
source hash to the later assertions. The 22 historical tests and this longer
test ran in separate processes to retain the 60 s bound per process; there
was no combined 23-test invocation.

From the repository root, using only existing Python/NumPy:

    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 timeout --signal=TERM --kill-after=2s 60s bash -c 'ulimit -v 524288; ulimit -t 60; taskset -c $(awk "/Cpus_allowed_list/{split(\$2,a,\",\");split(a[1],b,\"-\"); print b[1]}" /proc/self/status) python -B -u -m unittest candidates.qwen35_chunk_strict_contraction.test_real_chunk_continuation -v'
