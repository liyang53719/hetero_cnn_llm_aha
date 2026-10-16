# Public PV16 numerical entry preparation

## 中文计划与当前边界

- 已完成：共享实际 Dense owner / A banks 的控制模型与 Public Host 完成围栏，
  见已发布的 `raw_kv_public`。独立的合成 M128 Attention 数值结果已通过。
- 已完成：原始完整 Public PV16 数值入口默认关闭开关、两种独立源码组合、
  118 项来源冻结；17 项冷测试在普通及 -O 模式通过，两种组合也均通过。
- 进行中：最终独立审查和新鲜输入/参考重建方案。本目录没有真实完整数值结果。
- 下一步：先补齐并验证原始输入、参考与 official-BF16 库，再执行单次 M16；
  取得同源码、同模式的成功凭据及实际耗时后，才能审查 M128 运行。
- 待完成：完整 29 节点验收、消费者 RTL 连接及硬件性能验证。软件耗时与
  模型事件计数不是硬件周期或利用率。

## Exact existing execution path

The target remains `dense_block_reduce.check_public_numeric` →
`ReducedPublicExecution` → `OfficialPublicExecution` → `PublicExecution`,
using the original public21 prefix and suffix drivers, one Dense owner, one
Matrix service, and the official BF16 MLP policy. The separately prepared PV32
runner is not selected. Historical source commit
`38b943cdf6a0e2d642a1aef07b30e6d23e3ceed8` and its published receipts establish
lineage only; they do not certify this extension.

The original entry accepts rows 16 or 128. M16 is its smallest supported case.
The new enabled profile is restricted to M16 pending a reviewed same-source,
same-mode successful M16 prerequisite for M128. Disabled behavior retains the
original row domain and budget. Neither historical M16 nor standalone synthetic
Attention PASS may satisfy that future prerequisite.

## Source identity contract

Preparation uses separate fresh trees for disabled and enabled modes. Disabled
composition retains the original public sources and strict V4 execution
inventory. Enabled composition applies the published two public hooks and an
explicit observer contract variant. Its canonical flag is bound into the
snapshot and propagated through observation entry and exit checks.

V4's six reviewed replacements remain exact. Preparation freezes 118 source inputs. Disabled composition emits one entry
file; enabled composition emits seven files. An early exact six-file composition
check rejects a mismatched source tree before prior preparation, runtime imports
or library prerequisites.

The enabled profile adds only the
two public-source replacements within the 75-file inventory, leaving 67
historical identities unchanged. Observer/helper variants outside that inventory
are separately pinned. An enabled tree requested as disabled must fail the
original V4 source check. No global hash-map substitution, arithmetic replacement,
reference injection or publication-fence bypass is permitted. The AST normalizer
proves equivalence of the disabled projection after removing declared identity
plumbing. Enabled semantics additionally rely on direct source review and exact
generated-file hashes; normalization alone is not a proof of arbitrary enabled
branches. A changed enabled branch must fail the generated-source pins.

## Numerical acceptance remains bounded

Historical full-chain receipts report 28 observed fields and 27 assigned official
gates passing. `softmax_fp32` is diagnostic and has no approved tolerance. The
explicit mask node is absent, and score/logit/probability/softmax observations
cover causal positions only: M16 observes 1,632 positions with 1,440 future
positions absent per field; M128 observes 99,072 with 97,536 absent.
`full_29_node_acceptance` therefore remains false.

The existing assigned operator and final-output tolerances remain unchanged.
Historical M128 auxiliary independent-self-cache failures for gate/scores/logits/prob
remain recorded; this work neither erases them nor claims a fresh arithmetic
fault. Full-graph comparisons must use the original sealed-output/reference
protocol, opening references only after actual completion.

## Run prerequisites and proposed limits

No numerical run is launched by preparation or cold tests. A first single M16
run would retain the original 900-second execution budget, with a proposed
930-second external process-group deadline. A run-only job could use a 20-minute
envelope; a fresh setup plus run needs its own proposed 30-minute job, with a
600-second shared setup cap and the same 930-second run cap. Setup timing is
not yet measured end to end and may fail this cap. The
historical M16 outer runtime was 499.323 seconds (498.473 seconds inner), with
278,028 KiB peak RSS. These measurements are planning evidence, not guarantees.
A direct/enabled pair would require two explicitly budgeted runs.

Historical M128 took 1,548.112 seconds outer and 462,512 KiB peak RSS. The
original maximum requested execution budget is 1,800 seconds. Added transport
overhead may exceed that ceiling; no automatic increase or archived budget
override is authorized by this candidate.

Execution currently requires assets absent from this preparation workspace:
original raw-input manifest and input/reference directories, a freshly verified
independent reference, and the strict official-BF16 native library plus build
receipt. The synthetic Attention CI library uses the legacy SiLU source and
cannot substitute for the required `sf_vector_bf16_v1` ABI. The original verifier
must check its exact four-source closure, compiler, arguments, paths and ELF
hash; a historical ELF cannot inherit acceptance after source changes.

Some consumed reduction/reference source files also require verified restoration;
restoring the 75 observer inventory paths alone does not make preparation runnable.
The next setup audit will identify the existing official regeneration scripts,
pinned model revision and hashes, and bounded CI network/storage requirements.
Fresh inputs, references and the strict library must be rebuilt and revalidated;
missing ephemeral directories do not justify inherited numerical acceptance.
Any reviewed weight download must stay in the private CI workspace with no
payload upload.

Only source and safe hash/status evidence may be published. Raw weights,
activations, reference tensors and private execution paths are not upload
artifacts for this work.

## Existing fresh-rebuild route under audit

The existing `scripts/collect_qwen2_layer0_payload.py` can retrieve the 13 pinned
BF16 tensors using bounded HTTP ranges without downloading the whole checkpoint.
The original `scripts/qwen2_layer0_model_gate.py` supports a complete original
Qwen2DecoderLayer M16 reference. Independent reduced-policy results must use
`dense_block_reduce.reference.builder` together with the original RMS source,
table and arena helpers; generic sequential QKV results are not substitutes.
The strict ELF is built and checked by `official_bf16.dense_silu` itself.

Fresh manifests include acquisition timestamps; fresh reference receipts include
paths and timings. Their hashes cannot be assumed to reproduce historical
receipts. A later reviewed fresh-provenance adapter must bind the unchanged
per-tensor identities and original producers while retaining archived guards.
This entry preparation does not yet supply that adapter.

Historical reference tooling used CPython 3.12, CPU Torch 2.10.0, NumPy 2.3.5,
and Transformers 4.40.1. Package/source identities and CPU threading policy need
explicit verification before a future run. Native arithmetic times alone exclude
download, imports, compilation and packing and cannot justify the setup cap.

The declared weight source is Hugging Face `Qwen/Qwen2-1.5B-Instruct`, immutable
revision `ba1cf1846d7df0a0591d6c00649f57e798519da8`. The 13-tensor/22-segment
ledger `config/payload_pins/qwen2_layer0.json` has SHA256
`190e1fca0edff7c783c6981a6759f57162e63c4754ffc0f3481df64de9d06f88`.
Range-only acquisition verifies the ledger and header, not the advertised
whole-checkpoint LFS digest. The existing official-forward runtime identity
checks its pinned model/config source bytes as well as package versions.

Required network categories are Hugging Face range downloads, CPU Torch's
`download.pytorch.org` index, PyPI/package hosting, and repository checkout.
Redirect CDN hosts are not fixed by the retained receipts; a future launch must
verify them without printing signed URLs. The measured raw tensor total is
94,382,080 bytes. The source-derived reconstruction subtotal is 394,440,704 bytes
including segment cache, readonly arena and reference exports, excluding packages,
binaries, logs and new DUT outputs. Additional workspace capacity must cover
those items. Historical acquisition timestamps span roughly 411 seconds but are
not a complete stopwatch because acquisition was resumable; they do not guarantee
a fresh setup finishes within 600 seconds.

## Source-only preparation commands

```sh
python -m candidates.qwen2_resident_matrix.raw_kv_public_numeric.prepare
python -m candidates.qwen2_resident_matrix.raw_kv_public_numeric.prepare --enable-raw-kv
python -m unittest candidates.qwen2_resident_matrix.raw_kv_public_numeric.test_entry
python -O -m unittest candidates.qwen2_resident_matrix.raw_kv_public_numeric.test_entry
```

These commands perform cold control/source checks only. The original observer's
actual numerical execution still requires CPython 3.12 without `-O`.
