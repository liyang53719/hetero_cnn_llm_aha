# Fresh M16：已验证结果与 M128 后续计划

## 已完成

- 修正后的真实 CI [38904754050](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/38904754050)，job 116985413928，于 2026-10-16 完成。安全终态为 `PASS_FRESH_PUBLIC_M16_OBSERVED_GATES`。
- 本次重新建立输入、两种独立参考和原生库，执行原始 PV16 ReducedPublicExecution 完整 Public21 软件链；沿用同一 Dense owner/banks、Matrix/Scalar 服务及 Host 完成边界。
- 27 个已分配官方 observed gates 通过，记录 28 个 observed fields；`actual_dataflow_pass=true`、`fixed_arithmetic_pass=true`、`native_acceptance=PASS_OBSERVED_ONLY`。
- 包装器总耗时 727.058014 秒。该时间包含重建及数值执行，不能拆解为没有保留的阶段耗时，也不是硬件周期或利用率。

`M16_EVIDENCE.json` 保存原始安全 summary、progress 和完整来源哈希清单，以及运行、任务和 artifact 标识。ZIP SHA-256：`84ec66b585b977e4a31555eda59bd5921c7db4c7d138857460ecbea06a117405`。actual receipt 哈希为 `f742740f3643bac1d22ad8f9626adf54229bf3f32e2f9e4ad7eeb75e5af85702`；私有详细 receipt 和张量未上传。

最终 summary 是终态提交。progress 中 `TERMINAL_RECEIPT_PENDING` 是先写进度、再提交 summary 的安全写入协议，不覆盖最终 summary 的 PASS。

## 保留边界

`full_29_node_acceptance=false`；显式 mask 和完整非因果位置覆盖仍不在本次 observed-gate 验收范围。没有新增 Scala/RTL PASS，也没有将先前独立 Attention M128 结果当作本链 M128 验收。第一次运行 38901691296 仍为 FAILED，其包装器序列化问题及旧记录不被覆盖。

执行过的 M16 launch contract、setup profile 和原始算术来源保持冻结；本结果文件不改变那些合同。

## 进行中 / 待完成

- 进行中：审计独立 M128 fresh profile，将本次 M16 安全凭据及其精确执行来源作为前置条件，显式列出允许的行数、配置和准入改动。
- 待完成：真正重建 128 行输入、arena 和两种参考；复核原始 PV16 调度、全部原始数值门槛及来源兼容性。
- 待完成：独立、明确的运行预算与失败清理方案。历史完整链约 1548 秒加已测独立 Attention loan 增量约 498 秒，仅是约 2046 秒的粗略估计，不能直接当作新运行保证。
- 待完成：短测试、独立审查后才可由发布方启动一次 M128 工作流。当前没有执行该新 M128 完整链。
