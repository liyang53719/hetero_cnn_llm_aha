# Optional historical Q/K Norm256 replay

No NumPy archives, downloadable weights, full native reports, or runtime provenance
are distributed in this directory. Git stores the extraction code and this guide.
Generated data remains local and ignored. Do not force-add these files.

## Required portable gate

The default `scripts/run_qk_norm256_candidate.py` executes the immutable official
Qwen3.5-0.8B embedding/GDN0/1/2 prefix and layer3 producers in fresh baseline and
AVX2 CPU-dispatch processes. It creates transient input/native/weight arrays under
`work/`, records new provenance, then verifies actual RTL against independent
integer and C arithmetic and the new native captures. The two executions yield
5120 head observations; no claim of 5120 distinct-valued inputs is made. Their
input/native array equality is explicitly reported. CPU-independent or historical
byte identity is not promised.

Install the pinned runtime and collect the three bounded payload sets as shown in
`.github/workflows/qk-norm256-candidate.yml`. Checkpoint revisions, tensor byte
ranges and per-range hashes remain in `config/upstream/qwen3_5_0p8b/`.

## Optional archival replay

`--historical-corpus` accepts only separately preserved original archives admitted
by the existing code-fixed hashes. If you possess the original native arrays and
reports, `extract_frozen.py` reproduces their extraction without native arithmetic.
It requires the exact historical report/array/weight receipts; a newly executed
CPU result is never substituted under a historical name. The optional historical
loader fails closed if any required byte differs or is missing.

Historical-only unit checks are explicitly skipped in clean checkouts without
these optional archives. Arithmetic, source admission, fresh materialization and
actual fresh-native RTL gates remain required. With the original archives supplied,
those historical checks run too. There is no downloader for unpublished Git blobs.

The Q layout is eight consecutive `[Q256, gate256]` groups, not global Q/gate
halves. K has two 256-wide heads. Cold/carried phases each contain 128 tokens.
Native norm expectations are extracted from the actual official producer trace;
raw Q gates are kept bit-for-bit. The unchanged per-source/phase/role numerical
limits are max absolute error <= 0.03125 and mean absolute error <= 0.005.

This is a same-input component/layout gate. Matrix production, memory transport,
Norm-to-RoPE composition, whole-tensor ownership, complete blocks and MAC90% remain
outside its acceptance scope. Only allowlisted summaries are published by CI.
