# 完整128 identity 观测集成：实际 CPU FAIL 保留

[源码、失败与部分流摘要](../candidates/qwen2_full128_identity_failure/README.md)

- `identity_m128_01`：root 父命令 flags 顺序错误，strict argv claim 在计算前拒绝。stderr 证明复合检查失败；精确错误顺序来自 root 命令历史，不伪造未保存的父 argv。
- `identity_m128_02`：修正 flags 且迁移 gate 身份后真实执行，原 3600 CPU 秒限额终止，worker -9/reaped，无残留；不是仅 startup FAIL，更不是数值 PASS。
- 保留流有 1,766,012 个完整 frame，无 END footer；QK 5,029 / PV 10,352 组服务义务已退休，最后记录在 token107/head10 的 QK keys48–63，仅接受 3/8 步。该位置不是 SIGKILL 精确指令；组服务完成不等于输出 ACK、数值正确或 Attention 终态。
- 比旧失败保留了更深前缀，但不能换算时间加速、完成率、单独优化归因或必需预算。原预算未增加。
- 无最终 reference、完整 protocol replay、全 public21 terminal、后缀、最终 mask/capture/runtime-policy 验收；原 M128/历史 bf16/fp32 FAIL 与 canonical 状态不变。独立 M16 Attention 组件参考闭环仍仅限自身范围。
- 仅新增 bridge/runner 两个原字节核心源码，其他精确公开源复用；配置仅角色化摘要/pins，不上传 raw events/tensors/header/权重/私有路径。临时未数值验证 helper 不在本包。
- 无 full29/RTL/硬件周期/MAC 利用率/90%目标或性能采纳结论。
