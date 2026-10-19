# Recover the original frozen N0 reference

Source preparation only. No reference arithmetic, native runtime import, RTL build/run, model or wheel download, repository modification, CI run, or publication was performed. `test_cold.py` is standard-library-only. Official package metadata was read to complete exact wheel byte/URL pins; no package bodies were fetched.

## Accepted result and scope

`n0_reference.py` is a fresh, one-use, offline worker for only the original M128 N0. It compiles the entire unchanged official `Qwen2RMSNorm` class AST from the fixed upstream file. It takes the exact original BF16 raw embedding rows 0..255 and gamma0, binds rows 0..127 and gamma exactly as the existing fullblock capture did, calls that class once under inference mode, and uses the existing native-BF16 and FP32LE-export expressions. There is no rewritten RMS formula, independent NumPy recipe, fullblock execution, M1 loop, fallback implementation, or relaxed comparison.

Success requires both original hashes, not a new bootstrap:

- Native BF16: 393216 bytes, SHA256 `bd41672e6ea7d12746b41e56d21b3309369ecfd87cc26319ae6adbf0874e5cf2`.
- FP32 exact BF16 widening: 786432 bytes, SHA256 `3c25077e0b7aa5819df6fb93cbaba6a0d5379ac06b9df468beecd0f259b5cc3f`.
- Full output shape [1,128,1536], contiguous stride [196608,1536,1], storage offset 0, BF16 finite values. No early rows can pass.

On exact success only, the worker emits `n0.f32le` and `RECEIPT.json`. On arithmetic identity mismatch it emits `n0.observed.f32le`, `n0.observed.bf16le`, and a mismatch receipt, without a canonical filename. These observations are retained privately; the unchanged frozen contract remains authoritative. Source/input/runtime drift or resource expiry yields NOT_COMPLETED, never a DUT numeric failure. A killed worker may be unable to create a receipt; the parent must preserve the supervisor's fixed failure status and refuse to consume any output.

No file from a prior reference attempt is accepted as input. There is no upload step. Never upload tensor payloads, native code/binaries, private receipts/logs, runtime/system inventories, or working directories.

## Same-job call contract

The parent must hash and execute the exact same captured `n0_reference.py` buffer, with the separately pinned PINS.json, under the existing bounded process supervisor. Source hot reimport or an unverified pathname launch is not sufficient. All data paths must be fresh same-job files from the fixed raw2 acquisition; this package does not acquire model assets. Both raw files may also supply the separately authorized canonical16 provider preparation, so download neither twice.

Required arguments:

- `--repo ABS`: same-job checkout root
- `--embedding ABS`: original 786432-byte BF16 rows0..255 payload, SHA `3cdd8eecf1d0948c6ebf40ca947875b7b706521733fa3107e934d3815e45c014`
- `--gamma ABS`: original 3072-byte BF16 input_layernorm.weight payload, SHA `ea77d5968e396420086f0c6c45c08df4ca4228e0c8a0be5d6ec5d0d247110a0e`
- `--runtime-root ABS`: isolated installed site-packages directory
- `--python ABS`: canonical resolved executable currently running this worker
- `--python-profile ci31214` (default), or `historical` only for the exact existing original interpreter identity
- `--out FRESH_ABS`: nonexistent child under an existing private directory
- `--pins ABS`: exact PINS.json
- `--shared-stop NUMBER`: existing same-job monotonic deadline
- `--execute`: required; omitted execution is a cold no-op

Use interpreter flags `-I -S -B`. Set only the required arithmetic variables `OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 OPENBLAS_NUM_THREADS=1 PYTHONNOUSERSITE=1`. Leave ATEN_CPU_CAPABILITY, MKL_CBWR, ONEDNN_MAX_CPU_ISA and DNNL_MAX_CPU_ISA unset. Do not override the original arithmetic dispatch to make a runner qualify. Runtime-root relocation is explicit; arithmetic library/source identities remain unchanged.

The parent consumes the result only if all are true: supervised phase returned 0, process-group cleanup confirmed, receipt status is PASS_FROZEN_N0_EXACT, reference_accepted and both exact booleans are true, and a fresh parent read of the output confirms the original size/SHA. Never infer success from filename, receipt alone, a historical pass or an unchanged numeric tolerance.

Safe public status is one of PASS_FROZEN_N0_EXACT, REFERENCE_MISMATCH, NOT_COMPLETED. The optional worker code is from a finite enum. Only publish an allowlisted summary: fixed status/code, fixed output byte denominator, expected hashes and exact-match booleans. All detailed metadata stays private. No runtime or ABI qualification is granted to RTL by reference success.

## Runtime closure and incompatibility

The original reference requires Linux x86_64, compatible CPython3.12, manylinux_2_28/glibc>=2.28 wheels, Torch2.10.0+cpu commit449b1768410104d3ed79d3bcfe4ba1d65c7f22c0, NumPy2.3.5, native CPU dispatch AVX512, Torch build SHA `4f3cd65dc58472ed223329fa5ab743d0a360e777accb4001b511fc418c78128b`, 4 intra-op threads, 1 inter-op thread, deterministic algorithms. The five native arithmetic files and four existing Torch source files are byte-pinned before and after. Package import paths are checked. No Transformers package or model loader is needed: the official class is extracted by AST.

For CI, use the already-recorded Python3.12.14 executable identity from `candidates/qwen2_fullblock_ci_execution/platform.py`: 17752 bytes / SHA `bef88f140b625959f8af25c7b75cce2cd5d4b29cc2f2b079befd7f68eda4dba0`. This is an explicit platform binding, not a claim the Python binary is the historical one. The alternative historical interpreter remains 30894944 bytes / SHA `fa67443527ed9647f760d807e2a38f26340757123e643c4639cf273ed15d5ea7`.

AVX512 and four intra-op threads are existing reproduction requirements. If the Actions runner has only AVX2, an unrecognized Python ELF, a changed library, or a different build config, stop NOT_COMPLETED. No AVX2 candidate profile or new runtime identity is selected automatically. There is no evidence today that the next runner will meet these conditions, and no local pinned runtime was found.

`requirements-runtime.txt` is unchanged from the existing 11-package CI runtime source. `WHEELS.json` records the exact packages, official URLs, hashes, compressed byte sizes and metadata provenance: 11 wheels total 215906086 compressed bytes (Torch188943803, NumPy16606086, other nine10356197). `requirements-direct.lock` projects those exact URLs/hashes for future one-job acquisition. Install wheel-only/no-deps/no-index from previously verified files with no unpinned resolution, source distributions, extra dependencies, retries or model packages. If acquisition is later authorized, the parent must preserve all existing acquisition supervision/privacy requirements and verify exact sizes and hashes before install. This package does not execute pip or install anything.

## Finite budget proposal

Reference worker: 120 seconds work wall, 90 aggregate CPU-seconds, 8GiB hard virtual address-space cap, 4MiB individual file bound, no core files. Original reference budget documented ~806MB prior M16 attention RSS and ~6-second historical attention reference runs; those are context only, not a new N0 estimate. The worker performs only ~0.75MiB input reads plus two streaming passes over pinned libraries (largest ~443.5MB), with tiny actual N0 activations. The allowance does not predict successful duration.

Parent supervisor additionally observes a process-tree sampled RSS soft limit <=1.5GiB and terminates on an observed breach, and enforces combined private output <=4MiB, retained/emitted logs <=64KiB, no descendants/process creation, shared stop and cleanup/postflight reserves. The address-space cap is deliberately larger than RSS because mapped native libraries and allocator reservations are not resident usage. RSS sampling is not an OS-hard RSS quota. Worker execution adds a process/network audit hook, no process launch API, SIGALRM and rlimits; the existing supervisor still owns kill/cleanup and hard failure classification.

Runtime acquisition, if separately admitted: one exact 11-wheel set, compressed body cap256MiB, installed tree cap1.5GiB, combined private disk cap1.75GiB, 300-second acquisition/install envelope. These are static admission caps, not measured time or installed size. Enforce with existing supervisor and reject overrun; no retry or cap increase is authorized here. Interpreter provisioning is outside this wheel-byte sum and must fit the existing same-job setup budget.

Prefer reference recovery before expensive RTL generation so runtime incompatibility or unchanged-hash failure stops early. Only after reference acceptance should the real current Host same-model/same-RAM first-N0 attempt proceed.

## Verification

Run from the isolated candidate using the repository as read-only source:

`N0_REFERENCE_SOURCE_REPO=/absolute/read-only/repo python3 -I -S -B test_cold.py -v`

The cold tests verify exact original source/AST and frozen identities, immutable denominator and dual-hash gates, failures on corruption/size drift/links/FIFO, no-op non-execution, one-forward structure, and finite-budget pins. Synthetic output-gate tests use mocked digests and are explicitly not numerical observations.
