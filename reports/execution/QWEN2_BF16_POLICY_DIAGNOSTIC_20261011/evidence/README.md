# Qwen2 official BF16 materialization diagnostic candidate

This source-and-report snapshot contains no checkpoint arrays, tensor exports, readonly arenas, ELF executables, or hardware changes. The two new repository files are `scripts/qwen2_bf16_materialization_candidate.py` and its test. Everything else records prior software observations for review.

Policy: `qwen2-official-bf16-materialization-v1-diagnostic`. Every candidate result remains `DIAGNOSTIC_NOT_ACCEPTED`, and the CLI returns 1 even when diagnostic node gates pass. Official eager BF16 RoPE materializes each product before the sum; this differs from hardware numerical contract v0. No threshold or Matrix precision was changed.

M16: both reference comparisons pass all 29 node gates, 12 semantic checks, and the existing FP32 softmax row-sum check. M128: final output and 15 principal stages pass against native BF16, but the complete gate fails native scores/logits and separately fails independent gate/logits/prob/scores. Existing failures are retained.

The final versioned receipts were migrated from the original exact C++/ELF observations without repeating numerical execution. Adoption verifies original raw20 hashes, reconstructs all29 views from raw outputs and the verified readonly arena, and binds them byte-for-byte to exports. M128 admission revalidates the same chain for M16. All28 materialized nodes are verified BF16-representable; the separate softmax_fp32 tensor is FP32.

The ordinary two-operator backend trace reproduces original native QR and scores exactly and proves oneDNN brg_matmul:avx512_core_bf16 dispatch. It does not prove instruction-level reduction or bias order. The subsequent conditional QK call on candidate-owned operands shows all99,072 active scores bit-identical to candidate, with4 masked-future arithmetic differences. The valid score discrepancy against official therefore propagates from upstream Q/K for this observed input.

For the precise node dtype/rounding table, source references, original FP32-vs-native BF16 gate distinction, exact candidate diff, and future hardware connection caveat, read `work/qwen2_bf16_candidate_m16_20261011/CONTRACT.md` and `candidate.diff`.

From the repository root, run the seven lightweight tests with an environment containing NumPy, pytest, and ordinary g++. The script reuses the repository's frozen recipe/native helper modules. Test command:

```
OPENBLAS_NUM_THREADS=4 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 python -m pytest -q tests/test_qwen2_bf16_materialization_candidate.py
```

Full numerical execution additionally requires the existing validated recipe/native run receipts and payload caches. An ordinary invocation accepts `--recipe-run`, `--native-run`, and `--out`. M128 also requires `--small-candidate`. Migration additionally takes `--adopt-observation` and `--observed-binary`. These caches are deliberately absent from this source bundle; the JSON reports identify their original artifact hashes.
