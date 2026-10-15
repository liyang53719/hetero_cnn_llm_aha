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
