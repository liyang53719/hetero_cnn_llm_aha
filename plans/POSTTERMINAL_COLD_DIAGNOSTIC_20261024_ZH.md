# 终态后 cold128 诊断与预算中止回归（2026-10-24）

## 1. 范围与当前结论

本批是可复现源码、合成控制测试、原始失败诊断和中文计划，不修改 full_driver、owner、Matrix/Vector/Scalar 算术、阈值、ACK、提交协议或原始运行证据。便携版本真实执行状态为 `TEMP_NOT_EXECUTED`。通过合成测试不等于通过真实 cold128 数值、完整 M128 cold/carried、full-block 或 RTL 验收。

原始冻结源版本为 `e65598b2eaf72fc168614c6a36dc66bc3be4bdcc`。终态摘要和启动器原文均为 `FAILED`，退出码为 1；运行只完成 24 条成功 owner 终态，第 25 条 carried128/O 终态失败。该失败记录的 `complete=true` 只表示已消费终态，不表示计算成功。失败 owner 没有发布输出、没有联合提交，`executed_fmas=0`、`numeric_fault=null`，已提交 generation 保持 1。

源码与终态时间关系支持“预算触发 abort，执行未完成”的运行分类 `INCOMPLETE`，不是已经证明的数值不匹配或 reset 协议缺陷。该分类不得覆盖原始 `FAILED`、owner 原因或退出码，也不得把前 24 条成功终态提升为全程通过。

## 2. 预算边界诊断

- 有界启动流程从剩余工作预算扣除 60 秒 owner-drain 预留；协调器到达窗口预算后覆盖控制为 abort。
- O 路径经 TypedDenseDriver 将 abort 转为现有 local_reset/Matrix abort，原 owner 保留 `local reset requires coordinated backend reset` 原因。
- 协调器保留失败原因、锁定状态、未发布输出与 generation 1；外层随后抛出 `actual did not complete`。不能将这个外层 RuntimeError 误说成底层 reset 异常。
- 第 25 条终态比“绝对 work-stop 减 60 秒”的名义边界晚约 0.3203 秒。但实际 abort 边沿没有单独记录，且相对预算在后续 run/window 启动时重新锚定，存在设置及读时钟偏移。此差值不是实测 abort 开始时间，也不是 drain 延迟。
- 不据此自动 reset、重试或接续已中止窗口，不复用部分 staging，不调整数值阈值。若未来需要明确 stop-cause/abort-edge 遥测，应另做冻结、审查与测试，不改写本次证据。

## 3. 便携实现的安全边界

路径及运行特有身份只能来自调用者显式提供、以 SHA-256 复核的配置；源码没有个人执行绝对路径或隐式默认运行根。配置不是自行授予运行许可的手段：仍须有原持有者确认的已终止 handoff、原始严格 cleanup 证据及相应 pin。

保留原 fail-closed 顺序和语义：终态/cleanup 门禁优先于 actual/reference 读取；原始 START/LAUNCH/CLEANUP 身份及截止时间对应关系不变；全部输入、源码、receipt、冷窗口输出与 native 参考身份前后校验；progress 不能掩盖最终完整性失败。原始 16 条冷窗口成功 receipt、19 个输出摘要、generation 及 carried 输入与前次提交根绑定必须完整。

诊断只读取已建立来源的冷窗口输出并调用原比较 helper，不启动 owner、不重新捕获 native、不调用完整比较入口，不把参考值回填实际执行。Conv 参考算术默认不执行，仅在显式选项与已审查 handoff 明确允许时选择；未选指标保留 `NOT_RUN_UNSELECTED` 与空 pass/threshold。聚合 `passed=null`，`combined_full_run_acceptance=false`、`full_block_gate_pass=false` 始终不变。

独立诊断的资源约束仍是指定 CPU、4 GiB 地址空间上限、300 秒工作/CPU预算、325 秒 cleanup 与 330 秒外层上限；这是 RLIMIT_AS，不是 RSS 或专用 cgroup 上限。只管理其新建子进程，不重建原运行的进程权力，不延长原截止时间，不进行自动重试。

## 4. 历史真实冷窗口诊断（与便携版本分开）

原运行终态与严格 cleanup 核验后，原 run-specific adapter 的独立诊断进程以退出码 0 完成，耗时约 11.445 秒，cleanup 确认成功。它只比较已形成的真实集成 cold128 结果，不重跑实际 owner 或整个官方块。原冷窗口 16 条终态、19 个输出摘要与 generation 1 的来源绑定已校验；已分配的 17 个节点/状态 gate 和 7 个 operator gate 均通过，Prep 保持未分配，聚合 `passed=null`。7 个 operator 条目包含与节点检查重叠的 QKV/Z/AB/端到端 SiLU，不代表额外 7 个唯一张量或独立测试。19 个实际文件对应 17 个已分配节点/状态检查、1 个未分配 Prep，以及由 operator 检查覆盖的 pre-SiLU 观测。

最终输出 max_abs 为 `0.001953125`，mean_abs 为 `5.045527416314144e-6`，沿用原最终输出阈值 `0.05 / 0.01`。FP32 state 沿用每元素 atol=rtol=`1e-4`；同输入 Conv/SiLU 沿用原 1 BF16 ULP 门槛。一般节点/最终输出不是 bit-exact 或通用 ULP 验收，摘要保留各项实际门槛及误差，不以阈值通过隐藏非零 bit/ULP 差异。

真实结果的执行源码是原 adapter，不是本批重新配置化的便携代码。旁附脱敏 JSON 明确列出原三文件 pin、完整报告/进程记录 hash 以及便携版本 `TEMP_NOT_EXECUTED`。不复制原报告、路径、原始张量或进程授权收据。该历史诊断已获 `PASS_SCOPED_INDEPENDENT_POSTFLIGHT`：独立复核重新哈希 23,832 项源码/运行时/参考 pin，并核对 19 个冷窗口输出、原 handoff 元数据、独立子进程的 cleanup 证明与原持有 Popen 的路径。结论限于真实集成 Qwen3.5-0.8B L0 cold128 的 16 个 owner、一次联合提交 generation 1 及已分配指标；`combined_full_run_acceptance=false`、`full_block_gate_pass=false`、RTL 未执行、Scala 资源映射资格未建立，carried 数值结果不从 cold 推断。

## 5. 源码和测试

不复制权重、NPZ、原始张量、native 二进制、私有 PLAN/handoff/cleanup/原始诊断收据。现有仓库 helper 以相对路径定位并保留原 hash：

- `full_compare.py`：`a3de68cba35a649e98fa76ce103731a31c90f79c179d8806232b274c933f3ec1`。
- `strict_cleanup.py`：`30458e67e84c362ff74d69a702624e91bc3c3089600dd36a2469d9ffd6ec4047`。
- `bounded_run.py`：`26039ae437f9296767ee65cf8303146eadfb61a3116f60e9196a4f68f5b0b380`。

PASS：新预算中止 receipt 回归与现有 20 项 AST/控制测试，共 21 项在独立无 Git 源码目录通过。回归执行原协调器 AST 与明确的合成失败 driver，验证 abort 转发、精确失败原因、第 25 条 receipt、generation 1、锁定状态和无输出发布；不声称重放真实 owner 或数值运算。

原非便携 adapter 的历史准备证据为 54 项 stdlib/mock 测试及 2 个隔离 CLI 门禁 smoke；不能直接沿用为便携改写后的测试通过。本批便携配置、门禁、adapter 与 launcher 的 75 项 unittest 方法已通过：terminal gate 37 项、cold adapter 25 项、launcher 13 项；其中一个 launcher 方法包含 2 个真实隔离 CLI 拒绝场景，不能再加算成额外方法。合并预算中止和既有进度冷测后共 96 项。冷 adapter 测试恢复模块范围内启用的真实 Python audit hook，并用 `sys.audit` 验证禁止 model/native/process/network 的约束，结束后关闭该模块范围以免影响独立 CLI smoke。便携运行时三文件的新 pin 及 `CODE_PINS.json` 的 hash 单列于摘要，与历史执行源码 pin 不同；这些测试不授予便携版本实际运行资格。

## 6. 验证和发布计划

1. 在独立工作目录完成路径配置化、源码 pin 对照、包导入与隔离 CLI 冷测；不改变原 adapter、源码根或运行根。
2. 独立审查确认无门禁降级、无私有路径/数据泄漏、无原始证据重写。真实诊断结论仅在原持有者提交完整、可复核终态后单独记录，便携版本仍标明实际未执行。
3. CI 显式发现新测试目录并记录源码与既有 helper 的前后 hash；不减少既有测试、不允许零测试或 skip 冒充成功。
4. 审核后才按 main 当前 expected-ref 追加小批差量，保留已有 router、GDN CI、保存节点和维护约定。发布后逐文件回读并验证该 SHA 自动触发的相关 CI，不重复手动 dispatch。
5. 完整 cold/carried 数值、state/history 全程联合提交、full-block 与 RTL 仍单独验收；本批不改变未完成、失败或 UNKNOWN 的历史状态。
