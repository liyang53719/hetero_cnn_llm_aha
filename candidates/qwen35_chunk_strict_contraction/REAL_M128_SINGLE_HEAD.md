# Complete M128 single-head chunk64 software staging

This is a separate diagnostic, not an amendment to the earlier intentional
abort tests. `test_real_m128_single_head.RealM128SingleHeadTests` executes the
original M128 Prep and both complete chunk64 stages of one actual `ChunkJob`.
The original owner returns and retires a successful staging receipt. This is
**not a complete model block, all-head execution, publication, or RTL pass**.

## Real execution and provenance

The unchanged `make_prep` fixture supplies synthetic raw BF16 Conv/AB boundary
inputs and readonly A_log/dt_bias parameters. It does not execute projection,
convolution, RMS, or pretrained checkpoint inference. The actual original
`InputPrepOwner`/`TypedInputPrepDriver` computes, writes, ACKs, and publishes
all 128 Prep rows. Head0 is active; the other 15 heads are zero-written in the
unchanged 6400-FP32-word core row layout.

That exact published allocation enters the unchanged original `ChunkOwner`
and `TypedChunkDriver`, with one M128 cold job, heads=1 and Dk=Dv=128:

1. Both chunk64 stages execute all 24 scratch matrices: gate accumulation,
   decay, products, transposes, UT/QK, both solves, prediction, value update,
   inter/local output, state update/decay/add, and BF16 output materialization.
2. Chunk1 uses the real ACKed scratch `next_state` from chunk0. Each of its
   1024 state beats is actually read 64 times for prediction, 64 times for
   inter output, and once for decay, totaling 132096 accepted carry reads.
   There is no second M1 call, per-token recurrence substitute, external warm
   state publication, or reference tensor injected into owner memory.
3. The complete chunk1 state is read from actual scratch, once per beat,
   and copied through the original driver's physical software transactions
   to the 65536-byte state_out staging allocation. All 32768 output bytes and
   all state_out bytes receive actual accepted write ACKs.
4. The original generator exhausts naturally with status=None and
   staging_complete=True. The test holds and then retires this real receipt;
   it never constructs a replacement result or converts an abort into success.

Only the existing `StrictProducerArithmetic` instance-local Add/Mul hook is
used. The original `_compute`, `_solve`, `_matmul`, `_binary`, `_mul_add`,
transpose, exp, transport, tick, ACK, and lifecycle methods remain identical.
The same original PrepScalar is reused; its Div/Sqrt/Softplus/ExpNegative
recipes are unchanged. Vector16 is only the original noncomputing lease shell.
No native Vector16 arithmetic library is invoked. The known native minnormal
flags discrepancy is not resolved by this software diagnostic.

## Independent numeric and work checks

Expected arrays never enter actual memory. The existing separate reference
helpers are reused unchanged, not copied from the owner:

- All 819200 Prep FP32 words match the existing Fraction/RNE row oracle.
- All 16384 initial cold-state words are +0 and ACK-complete.
- All 48 scratch matrices, 403456 FP32 words total, match independent full
  arrays: 201728 words for each chunk, including all of both next_state planes.
- Every one of 21172544 executed strict Add/Mul intermediate words matches a
  separate NumPy float32 operation at that same arithmetic node.
- All 16384 BF16 output words match independent retained/remainder/tie-even
  rounding, not the owner's rounding-bias implementation.
- All 16384 final state_out FP32 words match the independently computed
  chunk1 state, after their actual addressed copy and ACKs.

The references use ascending-K reductions with separately rounded Mul/Add,
+0 accumulators, raw sign-bit negation and implicit unit-diagonal solves.
They do not use BLAS, skip masked dot products, divide by the stored UT
diagonal, collapse signed zeros, or call owner arithmetic helpers. Decay uses
the existing Fraction polynomial-exp reference. This benign synthetic range
does not exercise zero/saturated exp output or pretrained-model accuracy.

Every executed strict flag is checked to be 0 or NX. There is no new
independent full-plane exception-flags oracle; existing directed flags tests
remain separate. Observed counts are 6726524 exact and 14446020 NX results.

`expected_work()` independently derives the complete per-phase transaction
and arithmetic budgets from row/column/K extents. The test compares the full
observed dictionaries, not just aggregate counts, and checks every accepted
request tag against its monotonically increasing sequence:

- Reads: 724160, comprising 3200 published Prep beats (204800 B) and 720960
  scratch beats (46141440 B).
- Writes and write ACKs: 27776, comprising 26240 scratch, 512 output, and
  1024 state_out beats. Scratch ACK bytes: 1679360; external ACK bytes: 98304.
- Strict Mul lanes: 10600448; strict Add lanes: 10572096.
- Width1 issues: 4416; width16 issues: 1323008. ExpNegative calls: 4418.
- Cumulative-gate terms: 128; masked upper-triangle positions: 4032.
- chunks_started=2, chunks_completed=2, owner_results=1.

These are software operations/transactions, not hardware cycles or measured
bandwidth, throughput, utilization, frequency, area, or QoR.

## ACK, ownership, and publication boundaries

The final output ACK of each chunk is held for three ticks. Chunk completion
cannot advance early; the accepted request/physical obligation stays fixed,
no arithmetic resumes, and both owner leases remain held. Before the final
state ACK, external credit remains write_bytes-64 and no success receipt
exists. That ACK is separately held for three ticks with the same checks.
Attempting to detach the strict hook while an ACK is pending is rejected.

Only the accepted final state ACK allows successful completion and resource
lease release. A held successful terminal remains stable, blocks a new job,
and is retired exactly once. The original owner is then idle, unpoisoned and
ready, and the hook can be detached and the original owner reset.

At retirement, scratch, output, and state_out all have complete physical write
and ACK coverage and intact guards. All three remain **unpublished**. Normal
typed reads and readable-span acquisition reject them even after success.
state_committed, history_committed and generation_advanced remain false;
expected_generation remains zero. This follows the original driver's joint
block-commit boundary. A single head's successful staging is not authority or
evidence to publish a production block or advance its generation.

## Bounded author execution

The first and only author attempt passed one test in 79.336 s, process wall
79.592 s, with peak RSS 72616 KiB. Runtime verification confirms one permitted
CPU, 512 MiB virtual-address limit, 120 s wall/CPU limits, one native-library
thread and no Python bytecode writes. There was no earlier failed launch,
timeout or numerical failure for this diagnostic.

The tested source SHA256 is
`8a050002e8a393980d109107e3eea3d950a9af4564e9a7f693245153a8d0b2c6`.
All 38 explicitly captured source/history files match before and after the
run. This is not a complete runtime import/dependency closure. The exact
test snapshot, plan, launcher, log, exit status, timer, source hashes and
result receipt are preserved in
`reports/execution/QWEN35_REAL_M128_SINGLE_HEAD_20261023/attempt1.*`.

An independent read-only run of the same source separately passed one test in
73.409 s, measured elapsed 73.553 s including import, peak RSS 72580 KiB,
exit 0, under the same verified bounds. Its 38 explicitly captured files were
unchanged before and after. That set uses the prior continuation review's
36 files plus this new test and the Fraction reference; the author's set
instead adds this new test and the prior continuation validation receipt.
Neither set is a complete runtime dependency closure. The reviewer created
no files; its exact reported metrics and scope are recorded separately in
`REAL_M128_SINGLE_HEAD_VALIDATION_SCOPE.json`. Author artifacts are not
presented as independent-run logs. No historical regression was rerun in
this increment; existing earlier source and evidence remain unchanged.

All earlier abort-test sources, receipts, and production files are retained
unchanged. No network, new dependency, JAR, native compilation, commit, push,
or cleanup is part of this increment. Existing Python/NumPy is sufficient:

    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 timeout --signal=TERM --kill-after=2s 120s bash -c 'ulimit -v 524288; ulimit -t 120; taskset -c $(awk "/Cpus_allowed_list/{split(\$2,a,\",\");split(a[1],b,\"-\"); print b[1]}" /proc/self/status) python -B -u -m unittest candidates.qwen35_chunk_strict_contraction.test_real_m128_single_head -v'

The five-block full RTL and complete-block goals remain open. This result
only closes the previously missing full second chunk and final state/output
staging for the one-head strict-software diagnostic.
