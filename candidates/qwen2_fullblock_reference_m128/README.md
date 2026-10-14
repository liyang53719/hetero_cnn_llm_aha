# Qwen2 M128 full-block official-AST source candidate

Status: **SOURCE ONLY / NOT CAPTURED / NOT FROZEN / NOT NUMERICALLY ACCEPTED**.
All CLI execution options and the capture API unconditionally refuse. The default
CLI checks pinned source, JSON metadata, AST identities and payload sizes using
CPython 3.12 stdlib only. It neither imports Torch/NumPy/Transformers nor opens raw,
producer or reference payloads. CPython other than 3.12 is unsupported, including
AST hashes; there is no cross-version normalization.

This new package leaves the published M128169-file and M16188-file execution
closures unchanged. Their exact SHA256 ledgers are in pins.json and checked
read-only. It does not change or inherit the outcome of either Attention run.

## Allowed cold checks

From the repository root:

    python -B candidates/qwen2_fullblock_reference_m128/recipe.py
    python -B candidates/qwen2_fullblock_reference_m128/recipe.py --action plan
    python -B candidates/qwen2_fullblock_reference_m128/test_cold.py

No output directories are created by recipe.py. Tests use only the new ignored
work/qwen2_fullblock_reference_source_20261014 directory if scratch is needed.
`--execute`, `--action bootstrap-capture`, `--action capture`, `--action audit`,
`--action actual`, output/input/authorization options, and direct capture() all
fail before numerical imports or payload opens. There is no enabling environment
variable or approved-looking receipt that can bypass the source-only latch.

## Official source and scope

Model checkpoint: Qwen/Qwen2-1.5B-Instruct, layer0, revision
ba1cf1846d7df0a0591d6c00649f57e798519da8. Official Transformers source is v4.40.1,
commit9fe3f585bb4ea29f209dc705d269fbe292e1128f. The exact existing source/config,
header and raw range manifests are pinned, as are original PyTorch SiLU/Linear
Python sources and native runtime identities. No download or installation is
part of this candidate.

The existing27 Qwen2 AST nodes remain intact. Added11 whole Qwen2 nodes are the
MLP class168–180, o_proj constructor231, decoder constructors730/732, original
residual763, o_proj313 and decoder776/779/780/781/782. The exact14-node activation
closure comprises12 unchanged ClassDefs plus original ACT2CLS and ACT2FN
assignments. The vendored activations.py is byte-for-byte the acquired official
source (SHA25610c37e915ce2b52d539a5b52ecaaf644e2b0c56d282db00778098d74342ebeee,
Git blob2355fb5fed678d0de6e2c53f52644a35a691a34e); SOURCE_RECEIPT.json is preserved
unchanged. Its original `silu: nn.SiLU` mapping, selected by original Qwen2MLP,
is used. No hand-written activation or substituted official expression is used.

Count distinction: **38 model nodes +14 activation nodes**, yielding29 named
boundaries. This remains an official AST subset with explicit wrapper holders and
handoffs. Complete Qwen2Attention.forward, Qwen2DecoderLayer.forward, DynamicCache,
the full model and Transformers imports are excluded. Rotary cache is explicitly
bounded256, while original config says32768; equivalence is not claimed.

## Raw-only plan and dtype boundaries

The proposal joins the pinned prefix8 and tail5 original raw manifests by exact
checkpoint/name/shape/dtype/range/hash, preserving their different schemas.
Input14 producer receipts are checked as metadata and file sizes only. Their
payloads are never arithmetic inputs to this reference. In particular gamma1 is
read as original BF16 raw, not the materialized FP32 gamma1 producer. Matrices
are loaded in original checkpoint shapes. No old reference, typed output,
actual result, zero substitute, intermediate preload or reconstructed historical
arena is read to compute an output.

All original parameters are replaced with fixed raw BF16 values and checked
before arithmetic; holders are eval and require_grad=False. Original RMSNorm
performs FP32 norm work, casts to BF16 and multiplies direct BF16 gamma. Original
QKV/RoPE/Attention, o_proj, residuals and MLP return native BF16. Original
softmax expression300 runs unchanged; a one-call return tracer observes its FP32
softmax result before the original BF16 cast. Existing tracers are refused.

Original MLP180 remains whole. Forward hooks observe gate, SiLU, up and down;
the down pre-hook observes the product. Exact hook order/count is
`gate, silu, up, act, down`, once each, and all hooks are removed in finally.
Observers record source tensor stride/storage metadata before copying; copied
values are not fed back into computation. The wrapper name handoff after
original313 is disclosed. Original763 saves x and original779 saves r.

The explicit BF16 mask is wrapper data, not an executed official mask helper or
a DUT-produced tensor: allowed/diagonal+0, future0xff7f. Its native/export hashes
remain separately pinned. cache_k/cache_v are **cold semantic aliases; DynamicCache
not executed**, captured before repeat_kv. Cache K equals fresh K exactly; cache V
has a fixed head-major/token-major equality with fresh V. All layout transforms
are named in pins.json, never selected by comparison error.

## Outputs and honest freeze status

29 names: x, n0, qr, q, kr, k, v, cos, sin, repeat_k, repeat_v, mask, scores,
logits, softmax_fp32, prob, pv, att, cache_k, cache_v, o, r, n1, gate, up, silu,
act, down, y. All native BF16 except softmax_fp32. BF16 exports use exact FP32
widening; softmax_fp32 is exported unchanged. Native hashes are computed from
logical contiguous native bytes, while stride/storage/contiguity describe the
actual observed native tensor.

Every candidate output hash, native stride, storage_offset and contiguity is null
and marked NOT_CAPTURED, including the first18. Prior18 frozen expectations are
kept in a separate field for fresh reproduction checks, never presented as new
capture evidence. No bootstrap or REFERENCE.json exists for this package.

## Storage admission

Exact FP32 export total32,571,392B plus native mask32,768B =32,604,160B per
capture. One bootstrap plus one separate frozen reproduction =65,208,320B of
payloads. Planned caps:34MiB per capture (35,651,584B),69MiB total (72,351,744B),
leaving7,143,424B for bounded source/boundary manifests, review and logs. The
future body accounts for bytes before publication. There is no second full native
dump. Raw13/role14 files and native runtimes stay in place. These disk totals are
not RSS or wall-time estimates, and do not cover a separate whole-block DUT run.

## Admission and remaining review

ADMISSION.json is a proposed gate contract, not permission. capture.py deliberately
contains an unreachable future body for source review. This revision is not an
executable capture release. Enabling it later requires a separately authorized
source change and independent review of the updated lifecycle, runtime/timeout/RSS
control, before/after seals, exact inventories and bounded failure receipts.
Source-only check_contract intentionally accepts only NOT_CAPTURED and must be
replaced with separately reviewed bootstrap/frozen schemas at that time; removing
one latch is insufficient. No numeric bootstrap should be attempted now.

Only after independent source review and explicit authorization: run one fresh
bootstrap from raw, review its observations, create a distinct immutable freeze
with captured29 hashes and review identity, then run one fresh frozen reproduction
from raw without reading bootstrap payloads. A failed run remains unsealed and
must never be overwritten or used to teach a comparator new accepted values.

An actual full-block driver is a separate task and contract. Its own raw-only
single launch, FullGraphMemory/SharedWorkspace, terminal/ACK observations and
post-seal oracle opening are not implemented here. Frozen reference arrays cannot
prove DUT29 coverage. Keep missing mask and97,536 unobserved future positions per
Attention field explicit; current observed causal positions are99,072 per field.
Native bit-exact acceptance and official tolerance acceptance remain separate.
Unchanged numerical policy: BF16 operator max_abs<=0.03125 AND mean_abs<=0.005;
y block max_abs<=0.05 AND mean_abs<=0.01; every assigned hidden gate must pass;
no NaN/Inf; exact mask/cache copy/layout semantics; softmax row-sum error<=2e-5.
softmax_fp32 remains DIAGNOSTIC_NO_APPROVED_FP32_TOLERANCE, passed=null. This
candidate claims no model/RTL execution, cycles, bandwidth, utilization or QoR.
