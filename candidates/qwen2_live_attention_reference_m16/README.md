# Qwen2 M16 independent Attention reference

Fresh raw-driven official-AST oracle for the M16 pc0..12 software diagnostic.
This package performs no DUT or RTL execution and claims no numerical acceptance.

The read-only input producer is `candidates/qwen2_live_qkv_inputs`; actual raw and
materialized inputs are `work/qwen2_live_qkv_inputs/published7b31_fix_v3/{raw,inputs}`.
Eight original BF16 checkpoint ranges (7,085,056 bytes) independently produce
embedding rows 0..15, direct-gamma RMSNorm, QKV, RoPE and pre-o_proj Attention.
Saved prefix outputs, M128 outputs, DUT outputs and typed outputs are never
calculation inputs. Existing prefix hashes are metadata-only reproduction checks.

The same 27 unmodified pinned official AST nodes used by the reviewed M128
reference execute, retaining D128, 12 query heads, 2 KV heads, six repeats,
past=0, eval/dropout=0 and a bounded 256-position rotary cache. Full Transformers
forward and full original configuration equivalence are not claimed.

All 18 logical contiguous exports use little-endian FP32. BF16 nodes are exact
widenings of native rounded BF16 values, while softmax_fp32 is the actual original
softmax call's FP32 return, observed without rewriting line300.

- x/n0/qr/att: [1,16,1536]; kr/v: [1,16,256]
- q: [1,12,16,128]; k: [1,2,16,128]; cos/sin: [16,128]
- repeat_k/repeat_v/pv: [1,12,16,128], native head-major
- scores/logits/softmax_fp32/prob: [1,12,16,16], native B/H/query/key
- mask: [1,1,16,16], explicit audited wrapper argument, not a helper result

The mask has 136 allowed +0 words and 120 future 0xff7f BF16 words. Every mask
word is checked; native BF16 and exported FP32 have separate hashes. Native dtype,
shape, stride, offset, contiguity and logical-byte hashes are recorded separately
from export representation. Q/K/repeat/PV token-major hashes use only the fixed
transpose(0,2,1,3).reshape(1,16,H*128) rule. Transformed PV must equal att exactly.
The DUT diagnostic has 1,632 causal score positions; the oracle's full matrices
are not permission to fabricate missing future-position DUT observations.

## Freeze and consumers

Source-only checks do not open raw/runtime/oracle payloads, import numerical
libraries, run a compiler, use the network or write outputs. Actual capture
requires explicit execution opt-in, unchanged pinned source/runtime/input bytes,
Python 3.12 and the exact environment in pins.json. No installs or downloads.

A first bounded bootstrap capture is explicitly unaccepted. Only independent
read-only review permits new source pins to freeze its hashes. A separate fresh
process must then reproduce the frozen reference before consumer use. The
accepted reader rejects bootstrap manifests and placeholder hashes.

Consumers retain the published API: load_pins, source_check,
verify_reference_metadata, read_reference_payloads. Pre-run verification reads
metadata and current native-library identities only. Oracle tensor payloads may
be opened only after actual outputs are sealed at the pc12-held boundary.
Metadata verification does not import Torch/NumPy or require the consumer's
PYTHONPATH/thread environment to match the capture environment.

New output paths are restricted to
`work/qwen2_live_attention_reference_m16_20261014/<run>/<stage>`. Existing paths,
aliases, symlinks and input/output overlaps are refused. No old package, pin,
source or frozen fixture is changed.

Cold check: `python -B -S candidates/qwen2_live_attention_reference_m16/recipe.py`.
Cold tests: `python -B -S -m unittest discover -s candidates/qwen2_live_attention_reference_m16/tests -v`;
repeat with `-O`. Bootstrap/capture/audit CLI flags match the M128 package.
