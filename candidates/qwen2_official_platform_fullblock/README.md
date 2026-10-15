# Same-job official-platform fullblock source candidate

## 当前前置诊断

已发布的首次完整 job 保留 FAILURE：两份完整官方参考成功，actual 步骤失败；
安全聚合因所需 RESULT/LAUNCH 至少一项缺失而 INCOMPLETE，不能推断已执行数值。
本地同入口初始化控制通过，尚未确定该 CI 失败原因。

下一笔使用独立 15 分钟、零 DUT 授权和新两份单次参考证书。
preflight_diagnostic 只执行绑定、原 initialized-control 和监督器首次写入前的
只读准入条件，绝不启动 DUT。总 deadline 在准备前建立；初始化 90 秒及两秒余量
必须同时放入剩余总预算和当前 120 秒步骤预算，否则拒绝启动。GitHub 15 分钟总限制继续有效。
仅固定阶段、源码模块枚举、行号及异常类别公开，详细 traceback 和参考数据留本地。
该诊断不生成/上传 artifact；旧完整作业的触发文件保持不变。
正常 75 分钟 job.actual 的固定政策不能接受新的零 DUT 诊断审批。

新增冷测：`python -B -m unittest candidates.qwen2_official_platform_fullblock.test_preflight_diagnostic -q`
及同命令 `-O`。这些测试不构成业务数值通过。

This new sibling has no default approval and is cold by default. It does not
change the original official reference package, historical comparator, failure
records, numerical driver, native arithmetic, statistics or hardware claims.

The only executable job actions are `admit`, `capture`, `actual`, `aggregate`.
A new external DUT_REVIEW.json must approve this exact source closure and the
fixed conditional policy, with two distinct new reference certificates under
candidates/qwen2_official_platform_fullblock_authorization/new01 and new02.
The reviewed constant redirects only the pair's authorization directory; it
never reuses consumed certificates or changes the capture namespace/protocol.

Both fresh same-job captures must pass original semantic, source/raw/native,
loaded-libpython, resource, seal and write/readback gates; all 29 complete actual
payloads and layouts must match. Only then may the reviewed binder create one
exclusive local binding and return its digest directly to the launcher. This
means policy conditions were met, not that a reviewer saw future private bytes.
Legacy expected output hashes remain diagnostics. Pair failure or drift blocks
binding and DUT. Capture records remain honestly unaccepted bootstrap records.

DUT admission rechecks the exact private metadata and current platform/native
files, never reference payloads. Its actual process retains the exact 14 input,
13 raw, 30 reference read surface. Reference bytes open only after the complete
21-completion/17-owner/one-launch-result seal. A real initialized audit probe
runs in CI without model arithmetic. The original source-gated, bounded runner
and supervisor execute exactly once under unchanged 3300/3330-second limits.

DERIVATION.json specifies exact original source hashes and finite byte-level
substitutions. Driver changes only redirect three imports and output paths;
original tail/statistics/runtime/platform modules are reused directly. The new
post-seal comparator keeps every original comparison and its old exact-copy
failure diagnostics, then tests final sealed physical actual['kv'] against this
same launch's sealed K/V producers. Complete ACK/4096-beat/typed pc9 and live
identity evidence is required. Official comparisons retain max/mean 0.03125/0.005
for operators and 0.05/0.01 for block output. Nothing claims model ticks are
hardware cycles; fixed-array opportunities remain 4096 MAC and five contexts,
with the original whole-block statistics and denominator unchanged.

Only the strictly allowlisted aggregate schema plus two fixed reference/cache
contract enums leaves CI. Per-output
hashes, dimensions, receipts, private logs, reference bindings and payloads stay
local. No source file in this package approves itself or starts CI.

Cold checks (45 tests, also run with `-O`):

```
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 python -B -m unittest \
  candidates.qwen2_official_platform_fullblock.test_cold \
  candidates.qwen2_official_platform_fullblock.test_gates \
  candidates.qwen2_official_platform_fullblock.test_metadata \
  candidates.qwen2_official_platform_fullblock.test_comparator \
  candidates.qwen2_official_platform_fullblock.test_aggregate -q
```

Tests cover real cold imports/source and gate construction, both captures' real
metadata readsets with sparse synthetic payloads that must never be opened,
final physical KV corruption, complete ACK evidence, original FP64 mean boundary
failure and signed-zero uint32 counts, and strict aggregate allowlisting. These
checks are never an actual numerical fullblock PASS. The real initialized CI
probe is still required. The orchestration guard is not an OS sandbox or a
general subprocess allowlist; the unchanged native verifier queries compiler
identity as part of its source/ELF verification.

## 中文计划与状态

- 已完成：新官方 CPU 平台同一 runner 的两个 fresh reference 已完整成功且 29/29 导出字节一致；这仅是参考验证，不是本包 DUT PASS。新接线 45 项普通/优化冷测通过。
- 进行中：独立审查本包固定源码 policy、两次新单用参考证书与 DUT 审批。缓存修正明确比较最终 sealed 物理 KV 与同次 sealed K/V；旧跨官方 exact 结果和旧 FAIL 保留。
- 待验：同一个新 CI job 再采两份完整参考，通过全部条件后冻结本地绑定，执行一次完整 fresh DUT。原 operator 0.03125/0.005 和 block 0.05/0.01 数值门不变；尚无本包完整 DUT 或 RTL PASS。
- 固定预算：两个 reference 各 120/122 秒，DUT 3300/3330 秒，单 job 总上限 75 分钟；无自动重试。模型 tick 不作硬件周期或硬件利用率。

## 2026-10-15 精确 stdlib 迁移与短诊断

已发布的首次短诊断停在 ctypes 路径/旧源码 hash 联合门，DUT 未启动。新平台绑定官方 CPython 3.12.14 固定 commit 的完整 ctypes 源码和 setup-python 精确根；旧本地文件含 PyDLL(None) 异常包装补丁，不能当作相同源码。CDLL 三方法 frame/FENV 门保留。官方同 commit 的 shutil 全字节与现有 pin 一致，无需迁移。公开来源见 STDLIB_SOURCE_EVIDENCE.json。

本次新单用授权目录为 qwen2_official_platform_preflight_authorization_v2，保留旧失败与已消费审批。仅复用 15 分钟 pre-DUT 路线，两新参考各 120/122 秒，初始化 probe 90 秒且启动前同时核 job/step 剩余至少 92 秒；无 DUT。路径与源码身份检查分行，继续原固定阶段/模块/行号输出，不新增私有数据输出。

完整冷测命令：

```
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 python -B -m unittest $(find candidates/qwen2_official_platform_fullblock -maxdepth 1 -name 'test_*.py' | sort | sed 's|/|.|g;s|.py$||') -q
```

当前这批新增精确 stdlib 身份回归；冷测不代替真实初始化或数值全链通过。
