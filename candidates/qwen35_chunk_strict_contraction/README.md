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

    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 timeout 60s bash -c 'ulimit -v 524288; taskset -c $(awk "/Cpus_allowed_list/{split(\$2,a,\",\");split(a[1],b,\"-\"); print b[1]}" /proc/self/status) python -B -m unittest candidates.qwen35_chunk_strict_contraction.test_model -v'

This bounds virtual address space to 512 MiB and execution to one permitted
CPU. The 60-second wall-clock limit covers the complete test process.

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
