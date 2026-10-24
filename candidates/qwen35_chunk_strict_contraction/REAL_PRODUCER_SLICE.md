# Real InputPrep producer to QK: bounded software diagnostic

## What actually executes

`real_producer_slice.py` and `test_real_producer_slice.py` add a separate,
explicitly test-only integration boundary. The actual path is:

1. Distinct synthetic raw BF16 ConvOut and AB rows are physically written,
   ACKed and fixture-published through `TypedMemory`. A_log and dt_bias are
   readonly raw parameters. These are upstream boundary fixtures, NOT proof
   of an executed Conv, projection, RMS, tokenizer, checkpoint or real model.
2. The original `InputPrepOwner._compute` and `TypedInputPrepDriver` compute
   all 128 tokens. One active head retains the original 6400-FP32-word / 25600-B
   core stride. All 15 inactive heads are explicitly zero-written and ACKed.
   Publication is withheld through the final ACK and held terminal, and is
   performed only by the real driver's accepted successful terminal.
3. The SAME `PrepScalar` and `TypedMemory`, and that actual published core
   allocation, enter the original `TypedChunkDriver` and `ChunkOwner`.
   A cold M128 job is admitted with heads=1 and Dk=Dv=128. Only head0/chunk0
   executes. Initial state zeros, cumulative gates, all key/query/value
   products, pair decay and both transposes come from original `_compute`.
   No q/kb/kt/pair operand tensor is injected or fixture-written into scratch.
4. The original row / 16-column-beat / ascending-K `_matmul` executes full UT
   and QK, including separate rounded Mul, rounded Add, and final pair Mul.
   Both complete 64x64 outputs receive all 256 physical write ACKs. Each final
   ACK is held temporarily to check that leases and ownership remain live.
5. After QK's final ACK, `_compute` issues the first `solve_v` RHS read. The
   test accepts this one read, asserts abort, and holds the outstanding read
   through actual owner `drain`. The response then drains WITHOUT resuming
   the generator with its data. No solve arithmetic or solve writes execute.
   The original held terminal is `Aborted`, not success. Detach is forbidden
   until drain and terminal retirement. Reset then restores the normal owner.

There is no full M128 chunk execution, second chunk, completed chunk,
state-carry, gated normalization, full block, or production-policy mutation.
Full128-token Prep is NOT equivalent to full128-token recurrent computation.

## Arithmetic is explicit and separate

The ONLY instance-local hook is `ChunkOwner._op`. It uses existing strict
integer-software FP32 `lane_model.add/mul`, now with 1..16 active lanes in this
new adapter. The source owner itself is unchanged, including fatal mask30.
One-lane cumsum/difference operations and sixteen-lane products/contractions
therefore use the same existing arithmetic primitive. Row/column/K may be
absent from producer context: faults retain safe diagnostic fields rather
than raising a secondary KeyError. Exact minnormal/flags3 remains fatal.

Prep still uses its ORIGINAL `PrepScalar` Add, Div, Sqrt, MulIeeeRne and
Softplus recipe. Chunk still uses original `PrepScalar.exp_negative`, including
its existing polynomial, separately rounded internal NumPy nodes, ignored
internal exception flags and |x|>=80 zero selection. NO new exp, exp cache,
transcendental approximation, FP64 workaround, FMA contraction or native
Vector16 call is introduced. The Vector16 object is the existing tests'
noncomputing lease shell; only original acquire/release execute. Native call
and lane counters remain zero, while strict software counts are separate.

Raw owner source-identity/report fields still identify the original owner,
NOT this test-only arithmetic substitution. Use the new validation receipt
and hashes for the substituted program. No Scala/Chisel/HardFloat simulation,
JAR invocation, native compilation, RTL, device, cycle timing, utilization,
frequency, area or QoR result is established. The existing native Vector16
minnormal flags discrepancy remains unresolved.

## Input range and numerical comparison

The fixture has 128 distinct raw input and computed core rows. Active Q/K/V
are bounded exact BF16 values, A_log=-2, dt_bias=1/8, A=-4..-61/16 and
B=-1/2..1/2. This deliberately modest synthetic decay range keeps every causal
pair factor above0.5. "Warm range" is numerical only: the admitted state is
COLD, and no pretrained accuracy, workload distribution or saturated-exp
coverage is claimed. Upper-triangle pair factors are exact zero; diagonal
factors are exact one. There is no causal contraction short-circuit.

Independent checks never feed any actual producer bytes:

- Existing independent Fraction/RNE `oracle_row` compares all 819200 FP32
  words of the 128-token Prep output, including inactive heads and padding.
- All 87040 words in chunk0 gates, q/k/v, kb/vb/kbg/qg/ke, kt/ket and pair are
  compared with independently assembled arrays. The existing Fraction exp
  oracle checks each cumulative/remaining/causal-pair decay. No separate exp
  implementation is added by this diagnostic.
- NumPy separate float32 Add/Mul checks ALL 2148512 strict intermediate
  result words during actual execution, not just final contraction outputs.
  All 8192 UT/QK final words additionally compare against independently
  constructed ascending-K, separately rounded full-plane NumPy reductions.
- Independent checks of exact exception flags remain the prior Fraction and
  strict-lane suites. This warm-range full-slice comparison checks result bits
  and asserts flags are only 0/NX; it is NOT an independent full-plane flags
  oracle. A focused new unit check retains the strict minnormal flags3 case
  without requiring matmul position fields.

## Actual software requests and memory

Full M128 Prep: 1666 reads, 51200 writes/ACKs, 3276800-B published core.
Initial/chunk0 producers before UT: 6304 reads, 6464 writes/ACKs.
Each UT and QK: 35072 reads, 256 writes/ACKs. One additional solve read is
accepted solely to exercise abort/drain, for totals of 76449 reads and 6976
writes/ACKs. The test observes actual accepted driver requests; the unchanged
driver rejects scratch reads lacking this owner's actual write ACK.

Strict Add/Mul counts are 1097728 Mul lanes and 1050784 Add lanes; 2208
single-lane issues cover cumsum and decay differences. The original shared
scalar performs 2209 ExpNegative calls in chunk0, without saturation or zero
outputs in this fixture. Native Vector arithmetic counters remain zero.

The actual `ScratchPlan` reserves 1679360B for heads1/M128, although only
446464B become written and ACKed before abort. Scratch stays unpublished.
The full input core and raw fixture storage also exist in Python TypedMemory;
this is NOT a physical SRAM allocation proof or a complete live-memory bound.
Original transpose uses a 16x16 FP32 local tile; original matmul uses the
existing repeated row/beat/K reads, NOT the proposed whole-plane panel cache.
No production Matrix lane capacity, physical bank-port or broadcast claim is
made. Requests/software ticks are never presented as hardware cycles.

No output/state byte is written, no output/state/scratch region is published,
no generation advances, and `chunks_started=1`, `chunks_completed=0`.
Full-job staging success is deliberately false.

## Bounded verification

The first launch wrapper failed before starting Python because `/usr/bin/time`
was absent (exit127). That log, exit status and source hashes are preserved in
`reports/execution/QWEN35_REAL_PRODUCER_SLICE_20261023/attempt1.*`.
Replacing only the timer with Bash's built-in `time` allowed the first actual
attempt (`attempt2.*`) to pass 2 tests in10.597s, process wall10.828s, under
one permitted CPU, 512MiB virtual-address limit and60s wall/CPU limits.
The historical validation receipts are unchanged; they do not qualify this
new code. `REAL_PRODUCER_VALIDATION_SCOPE.json` records the new source scope
and results, including the separate combined regression when available.

From repository root, use the existing installed Python/NumPy only:

    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 timeout 60s bash -c 'ulimit -v 524288; ulimit -t 60; taskset -c $(awk "/Cpus_allowed_list/{split(\$2,a,\",\");split(a[1],b,\"-\"); print b[1]}" /proc/self/status) python -B -m unittest candidates.qwen35_chunk_strict_contraction.test_real_producer_slice -v'

No network, JAR, compilation, cleanup, commit or push is part of this check.
