# Immutable historical RoPE input and output corpora

These are subsets of pre-existing real-prefix runs, not regenerated expected
values. Each of `local.npz` and `remote.npz` stores 81,920 pairs from cold/carried
M128, Q8/K2 heads, rotating split-half channels i and i+32. Array words are uint32
FP32 encodings; original native BF16 values retain zero low halves.

- `inputs`: e, o, cos, sin from saved native Q/K Norm and coefficients.
- `native_products`: saved native ec, os, es, oc. The source stores (-o)*sin;
  extraction flips its sign bit to express os consistently. This preserves ±0.
- `native_outputs`: the two saved native BF16 additions, never recomputed.
- `hardware_comb`, `hardware_pipe`: two actual pre-existing RTL outputs plus
  aggregated FP32 flags, copied from both validated text outputs and NPYs.
- `historical_arithmetic.npy`: the 2,055 pre-existing directed/random FP32 input
  rows, separately counted and never called real model traffic.

`provenance.json` pins original full arrays, original native/RTL reports,
original vectors and actual output text hashes, plus per-group mapping/runtime.
`scripts/freeze_rope_rounding_corpora.py` reproduces this extraction after checking
all historical source hashes. Its arithmetic recomputation count is zero.
The ablation runner separately pins every compact corpus hash.

Remote full native archive: GitHub Actions run 37559899983, artifact 11456093688,
commit 2cb5c6c439b38e361fc64ecdea70b18ee7156570, archive SHA256
9892a37713d63dfa2d3025d1f34b12a7f606e08b8faec919982bb2e612137b33.
https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/37559899983/artifacts/11456093688

The remote native arrays SHA256 matches the independently collected actual RTL
run 37559899826, artifact 11456566006, at the same commit. Timestamps make the two
audit report hashes different; their entire producer NPZ bytes are identical.
https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/37559899826/artifacts/11456566006

Local originals were saved before commit 2cb5c6c and remain anchored by its
committed `reports/execution/U00_2_ROPE_HARDWARE_ORACLE_20261007/saved_result.json`.
The local/remote arrays intentionally differ because their upstream CPU paths
differ. Both remain frozen and are never replaced by the current CPU's output.

Scope: conditional RoPE pair only. This fixture does not validate coefficient
generation, upstream Norm, nonrotating channels, packing/store, whole blocks,
end-to-end native fidelity, or useful-wall MAC utilization.
