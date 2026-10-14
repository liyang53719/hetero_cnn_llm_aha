# Qwen2 M16 QKV input recipe

Small source-only recipe for `liyang53719/hetero_cnn_llm_aha`, reviewed source
baseline `ae7607104b3f7bdcec5800e07ad9948502eb2718`. It remains reconstructible if the
original ignored recovery directory disappears. **Default status is
`NOT_EXECUTED`; publication of this recipe is not numerical or hardware acceptance.**

## Exact boundary

- Qwen/Qwen2-1.5B-Instruct, revision
  `ba1cf1846d7df0a0591d6c00649f57e798519da8`, layer 0, M16, tokens and positions 0..15,
  no past tokens, direct gamma (never `1 + weight`).
- Eight original BF16 tensors, 7,085,056 bytes total: first 256 embedding rows,
  input-layernorm weight, and Q/K/V weights and biases. The extra embedding rows
  preserve the existing exact source-range pin; only rows 0..15 become `x`.
- Nine inputs: `x`, `gamma0`, `wq`, `wk`, `wv`, `bq`, `bk`, `bv`, `rope`.
  Weights are contiguous input-major BF16 words, an exact transpose of the original
  output-major words. The other roles use little-endian FP32 containers. `x` has
  file shape `[16,1536]` and logical shape `[1,16,1536]`; exact BF16 widening shifts
  each original word left 16 bits. It does not round or change its value.
- RoPE uses the exact pinned ordinary-C scalar source and strict compiler flags.
  The complete generated 328,448-byte table must match its exact hash; the input
  holds raw FP32 cos/sin at the first 16 positions of `[2,1024,64]`, zero elsewhere.
  The rounded duplicated 256-row tables have separate exact hashes. BF16 rounding
  is round-to-nearest, ties-to-even; C uses FP32 nodes, no fast math or FMA contraction.
- The optional posthoc oracle executes exactly 15 hash-pinned official AST nodes:
  RMSNorm/rotary classes, rotate/apply helpers, QKV constructor assignments, QKV
  projection assignments, head reshapes and the two RoPE assignments. It never calls
  full `Attention.forward` or a layer forward. Nine oracle output hashes must match.
- The oracle initializes a 256-position rotary cache; the upstream config says
  32768. Evidence here establishes only the pinned positions 0..15, **not complete
  configuration equivalence**.
- Q/K oracle files are logical head-major `[1,H,16,128]`. The pinned historical
  producer exports `transpose(0,2,1,3).reshape(1,16,H*128)`. The audit applies that
  fixed address rule and compares the resulting SHA256 to recorded historical
  SHA256. The recorded 2026-10-14 recovery audit found all nine fresh reference
  hashes match the recorded historical hashes after this rule; packaging cold checks
  do not rerun that oracle. **The old raw archive was not restored or read for a bytewise
  comparison.** Layout is never selected by whichever produces a smaller error.
- References are posthoc oracles, never owner inputs or intermediate preloads.
  No QK product, attention, softmax, MLP, M128, full block/model, host owner driver,
  RTL, or historical PASS is covered by this recipe.

The subset has a new manifest identity. It cannot satisfy or replace the old
full-layer timestamped manifest
`582f34afe5c52633f5290b5ba071f76164193f59d6edfc0d949658fd1e9715d1`.
The five excluded full-layer tensors remain excluded. No fabricated timestamp,
whole-checkpoint LFS verification, or inherited acceptance is claimed.

## Cold use: no dependencies or data required

Run from the repository root, using Python 3.12 (the AST pin/runtime baseline):

```sh
python -B -S candidates/qwen2_live_qkv_inputs/recipe.py
python -B -S -O candidates/qwen2_live_qkv_inputs/recipe.py
python -B -S -m unittest discover -s candidates/qwen2_live_qkv_inputs/tests -v
python -B -S -O -m unittest discover -s candidates/qwen2_live_qkv_inputs/tests -v
```

The default command checks the hash-bound pin file, 18 Git/source dependencies,
8-tensor/9-input/15-AST/9-reference coverage and scalar C source hash. It reads no
payload or ignored recovery data, imports no Torch/NumPy/Transformers, opens no
network connection, compiles nothing and writes nothing. The tests exercise
stdlib metadata and rejection gates using synthetic scalar/address checks, not
model fixtures. A subprocess audit hook blocks network, child processes, writes,
ignored-work reads and optional numeric imports during the default check.
Normal and `-O` run the same explicit `need` guards; runtime guards never use
Python `assert`. Test logs stay under ignored `work/`; only a concise summary is
publishable. This focused suite does not imply full repository CI acceptance.

## Explicit local reconstruction, only when requested

These commands describe future opt-in work. They were **not executed** to package
or cold-test the recipe. No install or download occurs automatically. Keep output
paths in the exact dedicated namespace
`work/qwen2_live_qkv_inputs/<run-id>/<stage-id>`. Both components are 1..64 ASCII
letters/digits/underscores/hyphens, beginning with a letter/digit. No absolute paths,
symlink components, traversal, arbitrary URLs, arbitrary caches or arbitrary roots
are supported. `--root`, if supplied, must equal this recipe's checkout root.
Unrelated Git HEAD changes are acceptable only while every exact source pin holds;
never update pins to make a failing reconstruction pass without review.

1. Obtain only the eight pinned ranges, with explicit download approval:

```sh
python -B -S candidates/qwen2_live_qkv_inputs/recipe.py --action acquire --execute --download --out work/qwen2_live_qkv_inputs/run01/raw
```

Requests use the fixed official revision URL and fixed ranges, each no larger than
4,718,592 bytes, eight ranges totalling 7,085,056 bytes. HTTP206, Content-Range,
Content-Length, identity encoding and payload SHA256 must match before acceptance.
The whole 3,087,467,144-byte checkpoint is not fetched or hash-verified.

If the original frozen directory is still present, use this alternative instead:

```sh
python -B -S candidates/qwen2_live_qkv_inputs/recipe.py --action acquire --execute --reuse-frozen --out work/qwen2_live_qkv_inputs/run01/raw
```

It validates the exact original subset manifest, each standalone receipt, receipt
identity and all eight payload hashes **before creating output**. It copies to a
fresh identity and labels the acquisition `verified_frozen_copy`; it retains the
original receipt acquisition times and does not claim a new download. It never
rewrites the frozen data or manifest. Only that precisely pinned frozen directory
is eligible; an arbitrary old/full-layer manifest is not a substitute.

2. Materialize input storage and generate RoPE using installed `/usr/bin/gcc`:

```sh
python -B -S candidates/qwen2_live_qkv_inputs/recipe.py --action materialize --execute --subset work/qwen2_live_qkv_inputs/run01/raw --out work/qwen2_live_qkv_inputs/run01/inputs
```

This uses stdlib and ordinary C only. Scalar C is extracted as a literal from the
exact pinned source without importing the diagnostic or its broader drivers.
Only `environment()` and `rope()` are called; the compiled RMS helper is unused.
Compiler command/version/binary/source hashes and the materializing interpreter
version/path/size/hash are recorded for this new build.
Different compilers/libm may fail the exact table hash; there is no tolerance or
cross-host identity relaxation. Generated C, shared object and build log remain
inside ignored output.

3. Optionally capture the bounded official reference in a fresh Python process:

```sh
python -B candidates/qwen2_live_qkv_inputs/recipe.py --action capture --execute --subset work/qwen2_live_qkv_inputs/run01/raw --inputs work/qwen2_live_qkv_inputs/run01/inputs --out work/qwen2_live_qkv_inputs/run01/reference
```

The locally installed runtime must be Python 3.12, NumPy 2.3.5, Torch 2.10.0+cpu,
Torch commit `449b1768410104d3ed79d3bcfe4ba1d65c7f22c0`, CPU capability AVX512,
threads 4, interop 1, deterministic algorithms enabled. The process must not have
pre-imported Torch/NumPy or set `ATEN_CPU_CAPABILITY`. This stage sets OMP/MKL
threads to 4 and OpenBLAS threads to 1 before importing them. There is no runtime
installer, alternate version mode or output-tolerance override.

Current interpreter, NumPy extension, Torch extension and three key Torch library
hashes are recorded, along with runtime/environment metadata. The exact Torch build
configuration text is SHA256-pinned separately; this is a configuration-text check,
not a claim that a historical process or its complete runtime was recovered. These are this
capture's identities; they do not establish complete historical runtime identity.
Transformers is not imported; only the exact selected official source AST executes.

4. Audit all newly produced artifacts to a separate fresh identity:

```sh
python -B -S candidates/qwen2_live_qkv_inputs/recipe.py --action audit --execute --subset work/qwen2_live_qkv_inputs/run01/raw --inputs work/qwen2_live_qkv_inputs/run01/inputs --reference work/qwen2_live_qkv_inputs/run01/reference --out work/qwen2_live_qkv_inputs/run01/audit
```

Audit requires the complete exact schema, including every provenance field;
missing, null, wrongly typed or unknown fields cannot become a verified receipt.
It checks scope, recipe identity, exact node names, paths, shapes/dtypes/bytes/hashes,
cross-manifest hash bindings, HTTP receipts, 15 official AST pins and runtime receipt
coverage. The generated C file must equal the pinned scalar source, the generated
shared-object bytes must match their recorded hash, and the full compile command
must match all fixed flags and source/output paths. The fixed local /usr/bin/gcc
binary hash and its --version line are compared to the build receipt without
compiling or loading that shared object. Python provenance must match the current
interpreter version/path/size/hash. Capture runtime metadata requires the exact
Torch build-text pin, fixed dispatch/thread flags, the complete environment object,
current Python import-environment values, current CPU affinity and the exact bounded
identity statement. Thus these receipts require the same local interpreter/compiler,
import environment and CPU-affinity context when audited; moving to another context
requires a new reconstruction, not relaxed checks. Historical comparison prose and
all nine comparison records must match their fixed pins and independently recomputed
layout/hash results. It independently computes the fixed Q/K
export-layout hashes, with no NumPy/Torch import or model execution. It writes only
`AUDIT.json` under a fresh independent output, never into any source directory.

The precise existing frozen artifact set can also be checked read-only, with a
new independent audit output and no need to run any reconstruction stage:

```sh
python -B -S candidates/qwen2_live_qkv_inputs/recipe.py --action audit --execute --frozen --out work/qwen2_live_qkv_inputs/frozencheck01/audit
```

This binds the four original frozen metadata documents by their recorded hashes,
then checks all eight raw payloads, nine inputs and nine reference outputs.
A frozen oracle runtime is identified as a prior capture, not the audit process.
This alternative depends on the frozen directory; the download reconstruction
route does not.

## Failure and publication rules

Every stage requires `--execute`, plus `--download` specifically for network
acquisition. Every output directory must be absent, even if empty. There is no
resume/overwrite/force mode. All files use exclusive creation. The initial 33-test result is preserved as
historical packaging evidence; subsequent metadata-hardening results supersede
its completeness claim without rewriting that history. Existing source
manifests, receipts and outputs are validated and read-only. Output/input overlap,
missing or extra roles, bool-as-integer metadata, source drift, mismatched range,
wrong model/revision, unsupported runtime or byte drift fail closed. Partial
outputs after failure receive no completed stage manifest; inspect them and choose
a distinct fresh identity for any authorized retry.

Only `.py`, this README, `.gitignore`, metadata/hash pins and the concise cold-test
summary are publishable here. The directory's allowlist `.gitignore` rejects other
new files. No tensor payload, array corpus, encoded payload, weight, ELF/shared
object, generated C file, log body or generated receipt belongs in Git. All such
local evidence stays under ignored `work/`. Nothing in the recipe authorizes
staging, pushing, model execution, downloads or publication on its own.
