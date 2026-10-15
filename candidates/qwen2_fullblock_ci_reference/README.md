# CI full29 reference adapter (source-only by default)

This is a **new bootstrap path, not a passing reference or DUT run**. No capture,
download, native import, review, GO, freeze, or numerical acceptance was performed
while preparing this package. Generated bindings belong only in the CI work area;
this package contains no copied historical receipt, frozen observations or new pins.

## Fixed boundaries

- Checkout: `/home/runner/work/hetero_cnn_llm_aha/hetero_cnn_llm_aha`.
- Fresh QKV raw/inputs: `work/qwen2_live_qkv_inputs_m128/ci01/{raw,inputs}`.
- All-fresh tail raw/inputs: `work/qwen2_live_tail_acquisition_m128/ci01/{raw,inputs}`.
- Python: CPython 3.12.14, executable resolved live beneath the verified
  `/opt/hostedtoolcache/Python/3.12.14/x64` prefix, exact observed 17752-byte ELF
  hash `bef88f140b625959f8af25c7b75cce2cd5d4b29cc2f2b079befd7f68eda4dba0`.
  No executable basename/alias is assumed. Other five native identities, AVX512,
  four intra-op threads, one inter-op thread and deterministic algorithms stay pinned.
- Original `capture.py`, supervisor and lifecycle are imported only after exact
  source hash checks. All 38 model AST nodes, 14 activation nodes, raw13 geometry,
  prior18 reproduction checks, 29 output geometry, guard budgets and limits remain.
- Oracle metadata preflight calls only the new tail `input_metadata()` reader,
  which delegates to metadata-only `metadata()`. It never calls a full tail audit
  or reads materialized producer operands. Original numerical capture reads raw13.
- Original 120-second bounded supervisor, independent watchdog, 1.5 GiB monitored
  RSS limit, one-use inherited capability, exclusive-slot GO, no retry, and audit
  boundaries remain. The lifecycle namespace is new, with additional review binding.

## Commands and review handoff

Cold source check (safe in a checkout without payloads):

    python -B candidates/qwen2_fullblock_ci_reference/recipe.py
    python -B -m unittest discover -s candidates/qwen2_fullblock_ci_reference -v

After separate authorized fresh acquisition/materialization and native runtime
initialization on the exact CI platform, generate only local observed bindings:

    python -B candidates/qwen2_fullblock_ci_reference/recipe.py --prepare-bindings

This exclusively creates `work/qwen2_fullblock_ci_reference/BINDINGS.json`; it is
marked unreviewed and confers no execution permission. The file binds the four
fresh metadata identities, observed Python path/identity, and current source
manifest. A failed preparation is retained, never overwritten/retried implicitly.

An independent reviewer must approve the exact source policy before bootstrap
and deliver the actual external static certificate as a separate work input.
The GO keeps its original exact schema. The review must additionally contain:

- `ci_binding_policy`: exact value of `recipe.bootstrap_policy()`
- `historical_receipts_revalidated`: false
- `observed_bindings_independently_reviewed`: false

The policy fixes root, input paths, output namespace, original pins, new Python
ELF identity and resolved-path prefix, other five natives, runtime requirements,
and unaccepted-bootstrap-only scope. It authorizes derivation and validation of
future metadata; it does not claim prior review of unknown receipt timestamps or
bytes. Each derived identity is retained as observed and checked at admission and
before/after execution. No self-signed approval is generated. The optional issuer only expands an actual
externally pinned certificate, and labels the resulting document as generated.

The review must live beneath `work/qwen2_fullblock_ci_reference/`. Its reviewer
must differ from the GO issuer. Review tool identity binds CPython 3.12 and the
source manifest; the separate target-runtime policy binds CI Python. The adapter
explicitly does not claim the review tool is the later CI executable. The issuer does not pretend that the reviewer authored its dynamic expansion.
The external certificate and expected source-closure SHA256 must be supplied by
the independently reviewed launch command, never extracted from the certificate.
Both stages require matching environment pins:

- `QWEN2_BOOTSTRAP_CERTIFICATE_SHA256`
- `QWEN2_BOOTSTRAP_SOURCE_CLOSURE_SHA256`

Before downloads, runtime initialization or observed bindings, perform static
admission only:

    python -B candidates/qwen2_fullblock_ci_reference/issuer.py --validate-only --certificate <external-work-certificate> --certificate-sha256 <external-review-digest> --source-closure-sha256 <reviewed-source-closure> --run-id ci01

After bindings preparation, explicitly expand that same actual certificate:

    python -B candidates/qwen2_fullblock_ci_reference/issuer.py --execute --certificate <external-work-certificate> --certificate-sha256 <external-review-digest> --source-closure-sha256 <reviewed-source-closure> --run-id ci01

This creates only the fresh `ci01/SOURCE_REVIEW.json` and `ci01/GO.json` beneath
this adapter's work namespace. The source review records
`generated_by=root-source-policy-issuer`,
`approval_basis=external_static_source_policy_certificate`, the exact external
certificate identity, the actual certificate reviewer/tool identity, and explicitly
unreviewed observed binding identities. The issuer refuses an existing directory.
Both issuer and lifecycle independently check certificate bytes, exact policy,
fixed original budgets, ci01/bootstrap-only scope and a recomputed aggregate
source closure. Capture boundaries also recheck the full aggregate closure.

The certificate's exact schema is enforced by `issuer.validate_certificate()`:
`schema`, `status`, `source_manifest`, `source_closure_sha256`, `policy_sha256`,
`run_id`, `mode`, `output_scope`, `maximum_invocations`, `no_retry`,
`exclusive_numeric_slot`, `numeric_executed`,
`observed_bindings_independently_reviewed`, `historical_receipts_revalidated`,
`frozen_mode_available`, `numerical_acceptance_allowed`, `budgets`, `reviewer`,
and `tool_identity`. No actual certificate is generated by this package.

After that independent certificate and explicit one-use GO only:

    python -B candidates/qwen2_fullblock_ci_reference/guard.py --mode bootstrap --run-id ci01 --go work/qwen2_fullblock_ci_reference/ci01/GO.json

This may produce only a sealed **unaccepted bootstrap observation**, with all 29
outputs and original audit evidence. It does not approve those output values or
permit an actual/DUT run.

## Remaining trust boundary

Frozen mode is deliberately rejected. Completing the pipeline requires review of
that new bootstrap, then a separately reviewed source change pinning a new frozen
contract and validating its bootstrap manifest/seal/review evidence. A subsequent
fresh, distinct frozen reproduction and its own one-use GO are still required.
The historical FROZEN_CONTRACT and unavailable historical work receipts are not
copied into this package or treated as evidence for the CI bootstrap. Exact original
source provenance remains in the original repository. No old pass is inherited.

The cold tests are source/control-flow and synthetic-input tests, not evidence
that this CI platform has generated raw inputs or executed a reference.

## 2026-10-15 接线修复与下一步

真实 CI 的输入准备已完成两次；完整 job 在参考步骤提前失败，DUT 未启动。
静态与冷复现确认：原 reader 漏接原生产者固定保留的 `rope_full.f32le`
和 `rope_build/`。本版本精确接纳该清单、固定元数据和无别名 stat，
不在 metadata 阶段读取 operand 或调用编译器；额外项仍拒绝。
此缺陷与该次失败相容，尚无原详细日志证明它是当次第一错误。

下一步仅新证书授权的一次 15 分钟以内 prepare→reference 集成诊断，
不启动 DUT。诊断输出限固定阶段/模块枚举和有界源码行号，详细记录留 CI 本地。
旧单次证书保持历史原字节；源码更新后旧闭包准入失败，不能自动重跑。

第一次短诊断已实际通过 prepare、fresh bindings、policy expansion，随后在 guard 阶段失败。
它的 guard 捕获异常后只有本地 JSON，旧 trace 提取无法定位。新增固定异常类别、
源码模块枚举/行号和固定阶段投影，覆盖 worker 与外层 supervisor，原异常/返回/清理
及计算均保持。下一次仅新单次证书的短诊断，不沿用前次授权；不上传异常正文。

### AVX2 独立候选（未获得数值结论）

仅显式 QWEN2_CI_RUNTIME_PROFILE=avx2-candidate-v1 且 ATEN_CPU_CAPABILITY=avx2 启用。默认 AVX512 runtime 契约不改；候选固定新观察 capability/build digest 与原五 native、Python ELF、线程、精度/顺序、原29输出期望。原 guard 的环境重建从候选 capture_environment 重新注入 avx2，所有 fresh worker 重验环境。prepare 先检查 Linux AVX2/FMA，防止官方 override 绕过硬件检测。

官方固定 Torch commit 449b1768410104d3ed79d3bcfe4ba1d65c7f22c0 的 DispatchStub.cpp 明确支持 ATEN_CPU_CAPABILITY=avx2，11893字节 SHA256 b77d16444f42d6e0707c581888d5e2069c7958a01ee4cf77a432bd6d13827032。来源：https://raw.githubusercontent.com/pytorch/pytorch/449b1768410104d3ed79d3bcfe4ba1d65c7f22c0/aten/src/ATen/native/DispatchStub.cpp 。该设置仅限制 ATen dispatch，不证明 MKL/oneDNN 或跨CPU结果等价；必须新一次参考实际比较。

单次参考预算15分钟：安装7分钟、prepare4分钟、capture3分钟，原内部120/122秒不改，无DUT。旧AVX512/旧runner失败记录保留；本候选的独立source授权只能用于本次参考，不能继承或放宽数值门。

AVX2首次实际运行38675911830已完成prepare，在参考capture.py第265行prior18精确一致性门失败，保留失败，不算参考通过。下一次独立授权仅补失败现场的只读固定枚举：节点NODE_00..17、HASH/LAYOUT/DTYPE/SHAPE/STRIDE/BYTES类别及不同字段计数；不输出实际节点名称、hash、shape、stride或tensor。该投影只解释首个失败的比较，不能代表全部18/29节点差异统计。原异常与数值门、原29期待不变；如涉及算术值差异，先重新审查平台/算术顺序，不直接改期待。

全已有输出诊断：38676537747确认首失败OUTPUT前的NODE_15，仅HASH三字段差异（源码映射softmax_fp32），无shape/dtype/stride/layout差异。下一次获独立授权的诊断在原失败catch对已经算出的29个outputs，仅沿原capture观察公式做精确BF16扩展、视图/连续化和本地hash。原计算链不重跑、tensor不写入、原失败状态不变，不seal、不声称通过。预先锁定既有原FROZEN_CONTRACT身份，外部只输出固定OUTPUT_00..28、类别和字段计数；空类别仅表示该既有输出的11字段匹配，不构成数值准入。

可复核tiny观察测试（不是业务PASS）：PYTHONPATH="$PWD/work/runtime_recovery/site-packages:$PWD" QWEN2_TINY_OBSERVATION_TEST=1 python -B -m unittest candidates.qwen2_fullblock_ci_reference.test_all_comparisons -q。使用本地现存Torch、7424个合成元素，核值/版本/存储地址不变；普通冷测缺runtime时明确跳过该项。

固定官方SoftMaxKernel.cpp显示最后维度FP32 softmax执行max归约、向量exp、sum归约及倒数乘；AVX2/AVX512为8/16通道、Sleef_expf8_u10/Sleef_expf16_u10，不同归约分组不保证逐位相同。仅源码机制证据，不推定本次误差大小或BF16落点。来源：https://raw.githubusercontent.com/pytorch/pytorch/449b1768410104d3ed79d3bcfe4ba1d65c7f22c0/aten/src/ATen/native/cpu/SoftMaxKernel.cpp 和同commit的 aten/src/ATen/cpu/vec/functional_base.h 。

## 显式 ATen GEMM 候选

新增 profile `avx2-aten-gemm-v1`，默认及原 AVX2 候选不设置 mkldnn。此候选保持原 runtime 三字段投影及原29精确期待，在原 `official-holder-construction-and-raw-bindings` 阶段（Torch 已核、算术未开始）显式设置并验证 `torch.backends.mkldnn.enabled=False`；后续 prefix/tail/观察及后验边界复核 False。策略作为本次 source-policy 独立绑定，不假称旧 runtime10字段已记录 backend。原 capture/官方AST无修改，fresh-import门不放松。该设置的根据是固定binary oneDNN false→ATen gemm_stub路径，以及合成探针发现 ATen AVX2 时 oneDNN 实际仍使用 AVX512_CORE_BF16；不先验保证逐位相同。参考仍遇旧期待差异立即FAIL，只观察已有29输出固定分类，不启用DUT或放宽容差。

## 双 fresh 自身复现诊断

仅在单笔15分钟工作内、同固定 disabled+AVX2 profile、同输入及native来源，串行两个fresh进程。ci01/ci02各有新独立单次证书和GO，不复用已消费证书、不删失败记录。第一次须恰在原capture265比较失败且私有29输出观察完整、前后source/raw/native/backend核验合格，第二次才启动。两次各120/122秒，原29期待与原退出2保持；安装7分钟、prepare3分钟、pair5分钟均受总15分钟外限。

失败观察只读取已有tensor，按native bytes写本地并逐文件读回，最后一次snapshot一致才写完成marker。两份共同source/raw/native/inputproof身份必须相同，仅各自certificate SHA不同为预期；每份34MiB、合计69MiB有界。父进程直接比较payload bytes与dtype/shape/原返回布局，公开固定OUTPUT枚举相等bool和same/diff计数。没有tensor/hash/shape值或私有元数据外传，没有SEAL/新正式reference PASS；全相等也仅表示同一runner两fresh复现。

候选算术审计（固定Torch449b176及原native binary）：BF16 Linear转置权重路径的F32 dot经8个8-lane FMA累加器，K1536为64元素×24组，再寄存器及lane按4→2→1树归约。已广播BF16 bias以F32加入后最终一次BF16舍入，不是dot先BF16再加bias。Softmax为F32 max/减法/Sleef exp/树求和/倒数/乘法，再模型独立转BF16。只称“F32 accumulate”不够定义硬件逐bit契约；FTZ/DAZ等浮点环境仍需后续明确。
- https://github.com/pytorch/pytorch/blob/449b1768410104d3ed79d3bcfe4ba1d65c7f22c0/aten/src/ATen/native/cpu/BlasKernel.cpp#L409-L438
- https://github.com/pytorch/pytorch/blob/449b1768410104d3ed79d3bcfe4ba1d65c7f22c0/aten/src/ATen/native/cpu/ReducedPrecisionFloatGemvFastPathKernel.cpp#L289-L303
- https://github.com/pytorch/pytorch/blob/449b1768410104d3ed79d3bcfe4ba1d65c7f22c0/aten/src/ATen/native/cpu/SoftMaxKernel.cpp#L63-L90
