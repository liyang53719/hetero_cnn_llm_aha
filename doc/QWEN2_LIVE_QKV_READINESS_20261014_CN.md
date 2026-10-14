# Qwen2 live QKV 当前就绪状态（2026-10-14）

## 结论与下一步

当前 main 为 `ab15242a7e7d346f5eff51eaffffb1688df9f454`，父提交为 `7b31b7f2650e1da3492d400633cac95ee2ba0ecc`。官方 M16 最小输入与新参考已恢复；当前主线是用这些输入执行与真实服务调度对应的数值模型，固定新源码、同次 producer 和原数值门，完成后独审。历史软件 PASS 不继承到新执行。构建条件满足后再跑同刺激 RTL，不继续反复分层构建大 Top。

五个最终 block 仍为 Qwen2-1.5B 完整 block、Qwen3.5-0.8B L0/L3、Qwen3.5-35B-A3B L0/L3。阶段预测至少 80%、争取 90%；最终同源完整实际 RTL 数值与固定资源完整周期 MAC 利用率至少 90% 的联合门不变。`U00.2 ongoing`、`U01 to do` 不变。

## 已就绪的输入与控制证据

- ab15242 的三文件修复仅将 TorchVersion 元数据 producer 正规化为 `str(torch.__version__)`；严格 reader、pins 和数值源码未改。冷门 normal/-O 各 47 项、各 472 项判决拒绝；这是元数据合同检查。
- 另一次 fresh 六进程执行全部 exit 0，7.606469486 秒，只覆盖 M16 输入恢复、C RoPE、15 节点官方 AST 参考及 audit。独审库存为 8 raw / 7,085,056 B、9 inputs / 6,928,384 B、9 reference / 458,752 B。没有 Host driver、QK、attention、MLP、M128、完整 block 或 RTL 验收；原始数据仍在 ignored 路径。
- `candidates/qwen2_live_qkv_inputs/COLD_TEST_SUMMARY.json` 的 SHA256 为 `021331b472f283d7c506b57c725f5f9e02da5f5a80a0ab91c39d5d69d7e0f607`。它保留执行时 base7b31 / candidate_commit=null 的候选身份；发布到 ab 后不得回写成旧执行的 source，也不得把 7b31 的原失败包装成通过。
- 唯一 payload CI：7b31 的 run `38544941392` / job `115788550944`，ab 的 run `38547506389` / job `115797098331`，均已核 exact-head guard、index PASS 和 38+38。只证明对应发布的 payload 合同 CI，未新增数值或 RTL CI；没有本地最终 receipt，索引不编造文件。
- ee6d0532eec49ae29626c639a34e7c6303c67d4b 的 Scala bridge 准备修复已在原控制 CI `38543196905` 闭环：33+33 冷门、实际 2 个控制 RTL 测试、22 markers。原 ZIP `work/ci_original_archives/11883625641.zip` 为 730,908 B，SHA256 `f3d38aa6415056c42a05875453cc9d207d93a83f738e324e1215a3085518d312`，exact-head、CRC、测试及四份 SV/FIR 已独审。真实 DUT 为 parser/coordinator/bridge，算术返回仍 mock；不代表全 Host 算术或数值性能通过。

## live QKV v5 的明确缺口

唯一读取的候选交付入口为 `work/qwen2_live_qkv_binding_20261014/FINAL_DELIVERY.json`，SHA256 `28eaa991c563d2281702932d646c2498c16a5c163521a02c47ad9fde9cd98da6`。候选仅在 ignored work，默认关闭与 baseline 评论外严格代码相等。完整 lint 因 signal 9 终止，原因未知；不得推断 OOM。

独立完整 XML 尝试设置 300 秒 / 2 GiB 预算，15.660 秒采样到 2,159,071,232 B 后主动 TERM，返回 -15；没有 XML。实际 M16 全 Host 算术、完整资源库存及全局依赖环均未通过，不以局部构建或旧软件结果补票。

静态 generated SV 仅给出部分库存：

- 49 个 FP32 ALU = 1 Scalar + 16 vout + 16 elem + 16 SiLU；Vector16 只是子池，不能缩成整个配置分母
- 17 个 DivSqrt = 1 + 16；七类 SRAM/queue 的数量和尺寸同 baseline
- SumBridge 新增 512-bit lhs 及控制 FF；外部 4096 MAC 的源码展开还不是完整 XML 库存验收
- M16 source 预测 useful/executed = 12.5%，只是有效/执行工作量比，不是周期 MAC 利用率。完整 launch 接受到最终 terminal 必须计入 DDR、依赖、供数、write ACK 和阶段间隙

后续仍需当前真实服务模型新执行及独审、global 依赖环与真实 adapter 集成、完整资源库存，然后在构建条件满足时做同刺激 RTL，最后推进 M128 完整 block。

## 历史通过与当前验收分列

Qwen2 cold M128、0.8B L0 cold/carried M16/M128、0.8B L3 cold/carried M16/M128 的指定 typed 软件门保留为历史范围证据；当前真实服务模型和完整实际 RTL 均需自己的新回执。35B 只到 prefix postnorm 和 saved-postnorm router logits，尚非 live postnorm 交接；top8/归一化 score、MoE、最终残差及 L3 完整链未完成。

## 本次维护边界与复验

仅维护当前 `doc/` 计划、唯一执行清单和本说明及元数据索引；不改 `plans/` 历史规划文件或兼容链接，不改模型/硬件/数值门、生产默认或任何旧 pin，不 stage/push。计划字节改变后同步清单的计划 SHA。

本次运行最小计划/checklist normal/-O 冷测试及 `scripts/check_generated_source_consistency.py` 只读预检。日志与完整结果仅保存在 ignored `work/qwen2_readiness_plan_sync_20261014/`；元数据索引 `reports/execution/QWEN2_LIVE_QKV_READINESS_20261014.json` 只含路径、size、SHA256 和状态。计划或预检 PASS 不代表数值、硬件或全仓 CI 通过。

实际复验结果：计划/checklist normal 与 `-O` 各 91 项通过；只读预检 normal 与 `-O` 各 14/14 PASS。`-O` 保留 pytest 的预期断言警告。初次默认解释器缺 pytest 的失败日志保留；随后仅使用仓库既有 `work/runtime_recovery/site-packages`，未安装依赖。清单独立 validate 通过，46 个父任务 / 62 个叶项，硬件验收声明为 false。
