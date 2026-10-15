# Same-input FFN gate diagnostic

This separate candidate changes no existing execution closure. It diagnoses
selected gate arithmetic, without running a complete MLP, full block, CI, or RTL.
Import and the default command are cold. Numeric execution requires `--execute`.

## Available inputs and limits

Local failed DUT attempts contain completed prefix outputs only. There is no
local completed DUT n1/gate payload. The separate frozen full-block files are
official references and are not DUT evidence; this probe refuses their reads.
CI private intermediates were not retained and are not reused.

Eleven pinned checkpoint raw inputs produce a new official-AST n1, stopping
before the MLP call. Only the original gate Linear is invoked, at original
[1,128,1536] input and [1,128,8960] output geometry. It uses the same relocated
six native binaries, ATen AVX2, MKLDNN disabled, four intra-op threads, one
inter-op thread and deterministic algorithms. All learned parameters are bound
to raw BF16 checkpoint bytes before use. The full-block reference's old build
metadata hash includes its AVX512 dispatch line. The diagnostic pins the exact
AVX2 metadata hash and verifies that replacing only that dispatch line restores
the original metadata hash; native binary identities do not change.

The gate-only official call has 1,761,607,680 logical MACs. Native Matrix arithmetic
samples three predetermined 32-column windows, all 128 rows: 12,288 values out
of 1,146,880. That is 18,874,368 observed physical FMA calls. Bounds per numeric
process are 120 CPU seconds, 4 GiB address space, and less than 64 MiB total
output. The documented shell uses an additional 180-second wall timeout. Output,
coordinates, differences, raw accumulators, and hashes stay under ignored work.
The probe prints only aggregate max/mean/element/difference counts.

## Gate arithmetic evidence

The source hashes in probe.py freeze these original implementations:

- `dense_block_reduce/matrix_binding.py`: split K1024+512 with pair reversal is
  dispatched only for q_raw, k_raw, v_raw. Gate uses the original dense adapter.
- `ffn_fullgroup/check_numeric.py`: K=1536 and one td_group(0,K,5) per production
  gate window, with ascending K and five independent contexts.
- `ffn_window/model.py`: the gate window overrides chunk_start=0 and
  chunk_end=job.k; no prefix accumulator spill or split sum applies to gate.
- `transposed_down/model.py`: the original packet mapper supplies weight lanes,
  activation lanes, padding, clear only at k=0 and terminal only at k=1535.
  Its original output_coordinate maps selected results back to logical rows.
- `ffn_attention/matrix_numeric.cpp` and `transposed_down/numeric_smoke.cpp`:
  the existing strict native kernel executes FP32 fmaf(weight,activation,acc)
  in increasing K order, retaining one accumulator through K=1536.
- `official_bf16/dense_silu.py`: only the final logical gate group is
  materialized with the original BF16 RNE helper; no partial BF16 or extra
  bias is inserted.

The probe directly calls that verified existing native library in standalone
mode, uses the original owner packet-mapping function and final RNE helper,
and checks its actual FMA counter. It reduces five independent contexts to one
for each sampled window, preserving each sampled cell's arithmetic. It does
not manufacture owner terminals, exercise the owner protocol, claim complete
resource equivalence, or replace the architecture with ATen's CPU reduction.

## Interpretation

This is same-official-n1 gate arithmetic isolation. It does not quantify how
CI DUT n1 error propagates into gate. Without genuine DUT n1 and matching gate
artifacts, that propagation remains unmeasured. A sampled comparison cannot
establish full-gate or full-block acceptance, even when every sampled value
meets the original unchanged max_abs=0.03125 and mean_abs=0.005 operator limits.

No proposed hardware arithmetic or numerical threshold is changed.

## Commands

Run from the repository root:

    PYTHONDONTWRITEBYTECODE=1 python -m unittest candidates.qwen2_ffn_gate_diagnostic.test_probe -v
    python candidates/qwen2_ffn_gate_diagnostic/probe.py

The numeric run is deliberately single-use at its fixed new private output.
Use the fixed Python executable from the runtime pins and the original
relocated PYTHONPATH. Set PYTHONNOUSERSITE=1, PYTHONDONTWRITEBYTECODE=1,
ATEN_CPU_CAPABILITY=avx2, OMP_NUM_THREADS=4, MKL_NUM_THREADS=4 and
OPENBLAS_NUM_THREADS=1, then invoke probe.py --execute under timeout 180s with
--native-receipt set to the canonical absolute path of an external local native
compile receipt and --native-receipt-sha256 set to its independently established
SHA256. The digest must not be read from a field inside that receipt. Both CLI
arguments are mandatory for execution; the default command remains cold.
A failed or existing output cannot be overwritten through a CLI argument.

## Historical observed local result (pre-portability repair)

The preserved pre-repair source at commit eb5f209 produced the following local
same-input sampled comparison. These are not execution results for the repaired
source; the repaired source has not been numerically executed:

- Sampled elements: 12,288
- Different elements: 2
- Maximum absolute error: 0.001953125
- Mean absolute error: 1.5895542067786059e-7
- Observed physical FMA calls: 18,874,368

These samples meet the unchanged operator limits. Full-gate acceptance and
upstream error propagation are explicitly unclaimed. The original CI gate
failure is not resolved by this result. It establishes that the fixed sampled
columns have much smaller gate-only error when both methods receive exactly
the same fresh official n1.

The original six cold tests passed at that revision. Two setup attempts stopped before any official model
or native FMA: the first correctly rejected a default tempfile write outside
the private output; the second rejected the AVX512 dispatch metadata hash
under the explicitly selected AVX2 runtime. Both are retained as failures.
The completed run uses fixed private temporary/cache paths and the exact AVX2
metadata projection described above; no numerical threshold or native identity
gate was removed. No failed attempt is relabeled as passing.


## Portability repair, without numerical rerun

The previous numeric entrypoint imported an untracked recovery helper. This
three-file repair removes that import and source pin; it does not publish the
helper, a private compile receipt, or CI-only fixed-root bindings. The original
probe, tests, README and local02 RESULT are preserved byte-for-byte under ignored
work, and the original local02 files remain unchanged. The repaired source uses
a new fixed local03 output; it has no new numerical result.

Before reading raw payloads or installing the no-subprocess audit, the entrypoint
checks the explicitly supplied receipt's independent digest, canonical absolute
regular-file paths, no symlinks, and the known existing library digest. It then
calls tracked dense_silu.verify_library, retaining all its schema, policy,
selected/original ABI, compiler, strict compiler flags, source closure and ELF
checks. That verifier's g++ --version has its existing 10-second timeout. No
library is loaded and nothing is compiled during this provenance preparation.

Receipt, ELF, compiler and native sources are rehashed before and after
verification, immediately before native loading, and after the diagnostic.
The later checks are read-only and launch no processes; the existing payload
and subprocess audit is unchanged. No receipt digest is hard-coded in source.

Fourteen cold/synthetic tests cover valid provenance through the actual tracked
verifier, absent/wrong external receipt hashes, schema/policy/ABI/compiler/flags/
source/ELF failures, alias rejection and mid-verification or later changes. They
load no native library or numerical runtime. Clean tracked-source validation
also runs with the untracked recovery directory absent; raw files and native
artifacts remain explicit local prerequisites for a future separately authorized
numerical run.
