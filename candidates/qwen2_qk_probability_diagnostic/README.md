# Bounded QK / probability diagnosis

This is a local arithmetic diagnostic, not a replacement implementation,
acceptance gate, full-block execution, CI run, RTL result, or throughput model.
No existing source closure or numerical policy is changed.

## Execution and identity

All entry points are cold unless `--execute` is supplied. The real run uses the
fixed recovered raw inputs, the six pinned native runtime files, ATen AVX2,
MKLDNN disabled, four intra-op threads, one inter-op thread and deterministic
algorithms. Official Q/K are regenerated from the pinned original upstream
RMS, projection and RoPE AST. QK uses the actual original BF16 `torch.matmul`
and scalar-division AST, never a Linear substitute. Runtime profile agreement
is not a claim of identical CI platform identity.

The comparison inputs on the historical branch are completed Q/K producer
records from an earlier locally failed full-block attempt, not the latest CI
outputs. Each record must have a terminal owner, exact byte ACK, finite payload,
matching payload hash and matching raw-input provenance. Known admission/audit
source drift is disclosed. Every other recorded old source identity must match;
no historical pass or complete source-closure pass is inherited.

`native_batch.cpp` schedules the original receipt-verified native Matrix ABI.
It does not implement its own FMA, alter selected matrix cells, or suppress the
original 16-by-32 native work. It extracts the original diagonal lanes, folds
sixteen FP32 lanes in order, rounds the completed dot to BF16, multiplies by the
original FP32 scale, and rounds the score to BF16. Its fold is checked against
unchanged statements extracted from the actual OfficialAttentionOwner AST.
The real run checks 310 coordinate/source combinations as words, including the
low-cost real-input pilot and observed worst positions. This checks arithmetic;
full owner memory/ACK protocol is not executed by this diagnostic.

Current softmax is the actual original owner arithmetic statements and original
ScalarService / exp_negative implementation, not a rewritten approximation.
The exact current Scalar comparison covers only sixteen selected real rows,
including the worst propagated probability row, with 1,796 causal positions.
It is not complete current-softmax coverage. Both official and current scores
are compared under the same softmax input, and probability propagation is
separately measured using the official softmax.

## Results and corrections

The four QK branches cover all 99,072 causal positions. The persisted-array
uint32 supplement confirms zero bit differences for each same-input
current-vs-official QK comparison and their completed BF16 dots, including
signed zero. Historical Q/K substitution produces twenty score differences.
The maximum score error is eight, at three positions. Each is two score-BF16
steps after a one-step change in the completed BF16 dot; it is not a one-step
score error. Actual values, coordinates and bit patterns remain private.

The original run used an explicit negative-infinity future mask adaptation.
The separate finite-mask supplement executes the exact pinned finite BF16 mask
and original AST nodes 20 and 21. It confirms zero causal probability bit
differences against both the adaptation and saved outputs. Because current QK
has no future observations, those future cells are explicitly diagnostic zero
fill before masking. This is not DUT future computation. The original run's
files and identities remain unchanged; the supplement records their hashes.

Same-input agreement isolates the observed local score error to propagated
prefix differences for these inputs; it does not prove correctness for every
input. Original gates remain unchanged and the full-block failure remains.

## Safety, bounds, and publication

The real run has CPU 120 seconds, address space 4 GiB, external wall 150 seconds,
and output below 64 MiB. An actual native-ABI pilot checks estimated cost before
all causal QK work. It completed in about nine CPU seconds with about 376 MiB
peak RSS and under 3 MiB output. No network, CI, upload or full block is run.

Detailed reports, native artifacts and all real arrays are stored only in the
ignored local work directory. Do not publish or upload those files. Only the
explicit SAFE summaries are candidates for aggregate reporting; those contain
fixed enums and aggregate max/mean/count fields, with no per-tensor hashes,
shapes, paths, values or coordinates. They are not acceptance receipts.

Cold tests:

```
python -m unittest candidates.qwen2_qk_probability_diagnostic.test_cold candidates.qwen2_qk_probability_diagnostic.test_supplements -v
```

A real run requires the pinned runtime environment and an unused fixed output
directory; repeated execution fails closed. Supplemental audits preserve the
original receipt rather than rewriting it. New execution requires a separately
reviewed output identity.
