# Fresh setup supervisor: separate preparation profile

## 中文计划

- 已完成：已发布的七文件来源验证器，40 个普通 / -O 冷测试通过。
- 已完成：单次 600 秒设置监督器的 25 个普通 / -O 冷测试，包含真实短时进程组清理。
- 进行中：独立 setup-v1 来源合同及监督器的来源审查。
- 待完成：真实生产器适配的实际验证、数值入口的双凭据校验和工作流审查。
- 未运行：包安装、权重下载、参考生成、原生库构建及新的 M16 完整数值链。

## Immutable base, explicit new provenance

The published `raw_kv_public_fresh` verifier and its pins remain unchanged.
The separate setup-v1 receipt must bind the exact base verifier/profile, setup
orchestration sources and resulting asset-manifest digest. This binding is
one-way: the asset manifest does not claim that its existing 183-input closure
contains the new supervisor.

Later numerical admission must explicitly require both linked receipts and check
identical raw-KV mode, selected source overlay, workspace, M16 rows and zero past
tokens. A standalone READY asset manifest does not satisfy this new route.
A later workflow addition requires a separately versioned setup contract.

Source freezing precedes every package or producer action. Recheck source and
artifact identities after child cleanup. Missing phases, identity drift or an
interrupted producer leave an incomplete setup receipt and nonzero exit.

## Fixed bounded phases

One absolute 600-second deadline begins before installation. Work uses at most
594 seconds, followed by at most five seconds for process-group cleanup and one
second for the safe final receipt. Phase caps draw from remaining time; they do
not add independent budgets: packages120, acquisition420, official60,
reference100, strict-library40 and final-hash20 seconds. An injected earlier
deadline may only shorten this envelope. No retry or automatic budget increase.

The original collector obtains 94,382,080 pinned bytes in 13 tensors / 22 ranges.
The original official gate runs both BF16 and FP32 modes once. Original sequential
and block/pair reference executables retain distinct output paths/inodes and
identities. The original strict BF16 library builder/verifier remains unchanged.
The readonly arena remains 188,043,264 bytes, with no intermediate preload.

Backend preflight must enforce Torch2.10.0+cpu commit
`449b1768410104d3ed79d3bcfe4ba1d65c7f22c0`, AVX512 dispatch,
unset ATEN_CPU_CAPABILITY and the original four-thread / one-interop policy.
Original source regeneration requires an actual verified Git checkout containing
only the reviewed consumed-source overlays; a standalone composed directory is
insufficient for `git show HEAD`.

## Failure evidence and later execution

All producer logs, model bytes, tensors, reference outputs and detailed local
receipts remain private. Shareable diagnostics contain fixed phase/status,
bounded counters/timings/hashes, allowlisted exception classes and verified
repository-relative frames/lines only. They omit exception text, locals,
commands, private paths and signed URLs. Evidence and private directories must
be distinct, non-symlink paths. Atomic progress updates cannot manufacture READY.

Setup feasibility within600 seconds is unmeasured. Package installation and
ranged acquisition may consume most of it. Completion requires genuine verified
assets; a timeout produces useful bounded diagnostics rather than inherited PASS.

A later M16 run retains the original900-second work budget. Its proposed external
limit is930 seconds in a separate reviewed30-minute setup-plus-execution job.
No workflow is installed by this preparation document. M128 remains gated on a
fresh, same-source, same-mode successful M16 execution and a reviewed runtime
budget. Original27 assigned observed gates and the unresolved29-node scope remain
unchanged.

## Cold verification

Run `python -m unittest candidates.qwen2_resident_matrix.raw_kv_public_fresh.test_setup -q`
and the same command with `python -O`. These tests use mocked producer commands
and tiny sleeping child processes only. They cover source-profile admission,
canonical metadata, bounded cleanup, private diagnostic filtering and interrupted
final commits. They do not install packages or execute numerical producers.

Public progress remains provisional. The successful safe summary links the private
SETUP.json commit by digest; both are required by the planned later admission.
A failure revokes this attempt's completion credentials. Incomplete final source
rechecks remain non-success, with the original failure diagnostic retained.
