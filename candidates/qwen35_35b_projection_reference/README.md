# Official 35B L0 QKV projection reference diagnostic

The fixed two-partial recipe passes the original `max_abs <= 0.03125` and
`mean_abs <= 0.005` gates against the complete pinned native QKV operator for
M16 and M128. It is not bitexact: the remaining differences are confined to
very small Q/K values. This folder does not enable an official production
driver role, execute a projection owner, or establish full-model acceptance.

## Exact scope

- Checkpoint: `Qwen/Qwen3.5-35B-A3B` revision
  `62704185bd97ad488cfc404e7caea797396b74dc`.
- Transformer source: `42ca97014c85d71a88ad60d55f08cb9fb4d26e2c`, pinned
  `Qwen3_5MoeGatedDeltaNet` initialization and first two QKV forward statements.
- Original complete BF16 weight `[N=8192,K=2048]`, bias absent. Inputs are the
  previously verified actual RMS owner's written BF16 `[1,M,2048]` outputs.
- The source's `self.in_proj_qkv(hidden_states)` statement and subsequent
  transpose execute directly. This is a new exact operator invocation, not a
  full native forward or an old capture reassigned to new inputs.
- Torch `2.10.0+cpu`, NumPy `2.3.5`, ATen CPU capability `DEFAULT`, one CPU,
  intra/inter-op threads 1, deterministic, no autocast, gradual host mode.

The independently compiled C never receives a native result or owner state.
It evaluates either all K2048 in increasing order, or independent FP32 +0
sums over `[0,1024)` and `[1024,2048)`, visiting each pair high first
(`ordinal XOR 1`), then one FP32 Add and BF16 RNE. Arithmetic uses the actual
libm `fmaf` symbol with strict compiler flags, and refuses FTZ/DAZ or an
incompatible rounding environment.

## Results

| Shape | Recipe | Bit differences | Max absolute error | Mean absolute error |
|---|---|---:|---:|---:|
| M16 N8192 K2048 | Two K1024, pair high first | 1,019 | 1.410593220986745e-37 | 2.2505764181058373e-40 |
| M128 N8192 K2048 | Two K1024, pair high first | 7,904 | 1.880790961315660e-37 | 2.1274863609995454e-40 |
| M16 N8192 K2048 | Sequential K2048 | 1,056 | 0.03125 | 5.057634098193375e-7 |
| M128 N8192 K2048 | Sequential K2048 | 8,119 | 0.03125 | 3.6862046215446753e-7 |

Every Q/K/V segment independently passes the same original gates. Pair V is
bitexact in both shapes. At the explicitly diagnostic output-magnitude
cutoff `1e-30`, pair differences are zero; sequential differences are 37 and
215. This cutoff does not replace or alter the acceptance gates. Most tiny
differences still have normal BF16 inputs and outputs, so this is not a claim
that all normal values agree.

All input and weight values are finite normal BF16. Pair C outputs contain
2/15 BF16 subnormals for M16/M128; the native outputs contain none. The actual
oneDNN verbose trace selects `brg_matmul:avx512_core_bf16`, with full shapes
`16x2048:2048x8192` and `128x2048:2048x8192`. Native JIT dumps contain
`vdpbf16ps`, `vaddps` in a merge variant, and `vcvtneps2bf16`. These dumps are
separate from the C/libm caller disassembly.

[Intel's instruction reference](https://www.intel.com/content/dam/develop/external/us/en/documents/architecture-instruction-set-extensions-programming-reference-737410.pdf)
documents instruction-local denormal flushing for these BF16 instructions,
independent of MXCSR. The observed tiny differences are consistent with that
behavior. No flushing was added to the C recipe or hardware policy, and no
universal equivalence to the native backend is claimed.

## Resources and provenance

The proposal retains five Matrix contexts, 4096 MAC lanes, Vector16 and the
existing 16-bank, 1376-word, 256-bit SRAM allocation (704,512 bytes). Two
81,920-byte partial slots coexist with the 524,288-byte A region. A full sum
adds M*N FP32 Adds: 8,192/65,536 Vector16 requests for M16/M128. Each request
adds two operand reads, one read-modify-write capture, and one physical
512-byte write. These are static counts, not measured hardware cycles.

`evidence.json` pins final and original reports, complete outputs, input and
weight provenance, compiler/libm identities, actual backend traces and JIT
dumps, per-segment results, and the bit-preserving NK-to-KN materialization.
Pytorch/oneDNN source files were fetched at exact commits and verified against
their Git blob identities. The oneDNN AVX512 blocking source selects K1024
when K exceeds 1024 with an untransposed input. This supports the proposed
split; numerical agreement remains bounded to the tested cases.

The first runs used normal-mode Python assertion guards and retained their
exact source snapshots. The execution runner replaced all 24 assertions with
explicit exceptions. An AST comparison proved that guard replacement was the
only code change; an actual optimized `-O` bad-input-identity run rejected
before arithmetic. Both full shapes were then freshly rerun under that
execution source; all three output hashes per shape match the original runs.

### Review correction: independent Q/K/V gates and verified recomparison

Review found that the initial aggregate gate could hide a segment failure.
For example, constant Q error 0.0078125 with exact K/V yields aggregate mean
0.001953125, while Q exceeds the unchanged 0.005 mean limit. The current
comparison requires the whole output and each Q/K/V segment to pass
independently. The finalizer enforces the same joint condition before claiming
acceptance. A failed numerical gate writes its failure report and exits 1.

The finalizer pins historical execution-report hashes, rereads and verifies
the current BF16/FP32 output bytes against those records, and recomputes all
whole-output and per-segment metrics from the verified BF16 bytes. Historical
timing and operation counts remain labeled as execution-receipt observations.
It verifies original/hardened output-byte equality and existing KN weight
bytes without rewriting them. The dilution, same-length output-tampering, and
optimized failure-exit negative tests pass with the four original tests.

No native or C projection was rerun for this correction. Unchanged raw outputs
pass all recomputed segment gates. Original execution receipts and pre-review
source/evidence snapshots remain in the existing output directories and
`work/qwen35_35b_projection_reference_20261013T0535/prereview_source/`.
`evidence.json` records the current comparison source separately from the
historical execution source.

## Reproduction

Run from the repository root using the restored runtime, one shape at a time:

```sh
ONEDNN_VERBOSE=1 ONEDNN_JIT_DUMP=1 work/qwen35_runtime_20261012_recovered/python.sh candidates/qwen35_35b_projection_reference/run_reference.py --m 16 --out work/new_projection_m16
ONEDNN_VERBOSE=1 ONEDNN_JIT_DUMP=1 work/qwen35_runtime_20261012_recovered/python.sh candidates/qwen35_35b_projection_reference/run_reference.py --m 128 --out work/new_projection_m128
python -m unittest candidates.qwen35_35b_projection_reference.test_reference -v
```

The source-pinned acquired payload and actual RMS producer files must already
exist; the runner never downloads them. Each shape has a 120-second wall/CPU
bound. Final measured numerical work was 1.04/7.69 seconds with about 442 MB
peak RSS. Host time is not hardware latency. The numerical diagnostic does
not feed expected values into an execution resource.

## 2026-10-13 recovery and fresh-input replay

The original reports above remain historical receipts. After the uncommitted
workspace disappeared, all 19 candidate blobs were restored by their Git object
IDs; their exact tree was `96a065ce7a3fb2e573ab8656f2996fe60e945d29`, based on
`a5f49a1d04eefbe4b9387fdc0417d4b50e23633f`. Restoring text is not a numerical
PASS. New raw payload, runtime and owner outputs must be generated again.

The runner now accepts `--payload`, `--manifest-sha256`, `--rms-output` and
`--rms-summary-sha256`. These bind a newly acquired payload and a freshly executed
RMS producer without changing the original checkpoint, complete `[M,8192,2048]`
operator, weight SHA, expected RMS input SHA, arithmetic recipe or per-segment
thresholds. The output directory must be fresh and under ignored `work/`.
The explicit `HETERO_35B_RUNTIME_PROFILE=recovery_20261013` profile checks the
new wrapper/receipt and the same original three Torch/NumPy binary SHA256s.
Historical defaults and receipts are retained, not silently relabeled.

`scripts/rebuild_qwen35_official_runtime.sh` downloads 16 fixed official wheels,
verifies every wheel SHA256, installs into a fresh isolated `work/` directory,
and emits a real import/version/dispatch/BF16 smoke receipt. Rebuilding produces
new receipt metadata: review and explicitly pin that new receipt and wrapper
before numerical use. Do not copy a historical receipt or change binary pins to
make a failed runtime pass. The script itself has syntax validation; the current
runtime was independently installed and checked before the script was packaged.
