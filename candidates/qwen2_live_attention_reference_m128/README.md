# Qwen2 M128 independent Attention reference

Local-only, fail-closed official-AST oracle for the fresh public21 pc0..12
software gate. This package does not execute the DUT, certify numerical gates,
run RTL, or claim complete Transformers/layer-forward execution.

## Independence and exact scope

A new process reads the same eight pinned checkpoint ranges and independently
recomputes real embedding rows 0..127, direct-gamma RMSNorm, QKV and RoPE. The
reviewed M128 raw/input package is a read-only dependency. Saved QKV/reference
files, actual outputs and typed-reference outputs are never calculation inputs.

The original 15 prefix AST nodes plus 12 additional unmodified official AST
nodes execute from pinned `modeling_qwen2.py`: repeat_kv and forward statements
280..311. `o_proj` at line313 and all subsequent operations are excluded. No
Transformers installation, cache implementation or tail weights are needed.
Cold/past=0 K/V are only this invocation's K/V, with 12 Q heads, 2 KV heads,
128 dimensions and six repeats per KV head. The rotary cache remains explicitly
bounded to 256 positions; complete original-config equivalence is not claimed.

The additive causal mask is an explicit audited wrapper argument, not a claimed
Transformers helper result. BF16 shape [1,1,128,128], diagonal/allowed words +0,
future words 0xff7f (FP32 export 0xff7f0000); all 16,384 positions are checked.
Its logical native bytes and FP32 widening have separate hashes. The mask is
not a DUT-observed arithmetic node.

## Exports and layouts

All 18 exports are logical contiguous little-endian FP32 files. Every BF16
value is widened exactly, with zero low16 bits; `softmax_fp32` is unchanged
FP32 captured from the actual return of the original softmax function. The
original line300 expression is not replaced or split. Dropout is eval/p=0.

- Existing nine: x, n0, qr, kr, v, q, k, cos, sin. All nine must reproduce
  the reviewed M128 pins freshly; this does not inherit numerical acceptance.
- repeat_k, repeat_v: [1,12,128,128], BF16, head-major
- mask: [1,1,128,128], BF16
- scores, logits, prob: [1,12,128,128], BF16, B/H/query/key
- softmax_fp32: [1,12,128,128], FP32, B/H/query/key
- pv: [1,12,128,128], BF16, head-major
- att: [1,128,1536], BF16, fixed official transpose/contiguous/reshape

Native dtype, shape, stride, storage offset, contiguity, logical payload bytes
and hash are recorded independently of the exported representation. Native
logical bytes do not mean all bytes of a tensor's backing storage.

`token_major_sha256` applies only the fixed transpose to q, k, repeat_k,
repeat_v and pv; other exports are unchanged. No layout is selected by error.
The byte identity between transformed pv and att is mandatory. The official
reference has full matrices; DUT causal coverage remains 99,072 elements per
score/logit/prob/softmax field, and this package does not synthesize absent
future-position DUT evidence.

## Two-phase freeze

The first capture is explicitly BOOTSTRAP_UNACCEPTED_NO_NUMERICAL_VERDICT.
Its source snapshot and unaccepted manifest must receive independent read-only
review before any new hashes are frozen. Only source-only pin changes then
permit a separate fresh process to reproduce all frozen output hashes.
A bootstrap manifest is always refused by the consumer's accepted reader.
Source/input/interpreter/compiler/native-library snapshots are persisted before
and after every actual capture/audit. Drift leaves no completed manifest;
partial output directories remain and cannot be reused.

## Interfaces and execution

The default `python -B -S candidates/qwen2_live_attention_reference_m128/recipe.py`
uses only stdlib, reads no raw payload/runtime libraries, and returns
NOT_EXECUTED. It neither downloads nor installs anything.

Capture requires explicit `--action capture --execute --subset <raw-dir>
--inputs <input-dir> --out <fresh-reference-dir>` and the exact capture
environment in pins.json. The input directories retain the reviewed M128
namespace. New outputs are restricted to
`work/qwen2_live_attention_reference_m128/<run>/<stage>`; aliases, symlinks,
existing outputs and overlaps are refused. `bootstrap-capture` is available
only while the source pins are explicitly unaccepted. `audit` additionally
requires `--reference` and performs only byte/metadata verification.

Consumers import recipe.py without NumPy/Torch and use:

- load_pins(root), source_check(root,pins)
- verify_reference_metadata(root,pins,subset,inputs,reference,subset_sha,inputs_sha)
- read_reference_payloads(root,pins,reference,manifest), only after actual
  outputs are fully sealed at the pc12-held boundary

The metadata-only function reads the manifest and checks recorded runtime plus
current native-file identities, but never opens reference tensor payloads,
imports numerical libraries, or forces the caller's PYTHONPATH/thread env to
match the capture environment. Runtime identity is limited to the pinned
current key libraries/interpreter, not an entire historical environment.

Run cold tests with `python -B -S -m unittest discover -s
candidates/qwen2_live_attention_reference_m128/tests -v` and repeat with `-O`.
All large raw/reference files, runtime libraries, logs and source snapshots
remain ignored under work/. No existing published package or math source is
modified by this package.
