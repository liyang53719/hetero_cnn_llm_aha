# 生产 M16 Attention 组件 r2/r3：保留 FAIL，不是数值验收

见 [源码与失败证据说明](../candidates/qwen2_production_attention_diagnostic/README.md)。本包只公开原字节源码、相对角色 pins 与脱敏审查摘要，不含权重、header 原数据、raw tensors/events 或私有配置。

- r2：`FAILED_RETAINED`，授权 operand 前缀解码后，完整源码校验遇到唯一 pinned header 元数据资格分类错误；尚未导入 DUT/加载 Matrix ELF/提交数值 job。CPU 0.6255342 s / wall 0.652715 s，child 1，清理收据无残留。原失败不改。
- r3：只修复 binding/policy/support/worker 四个源码文件的精确只读元数据资格；随后一次真实 M16 public3 Attention 固定顺序双臂仍整体 `FAILED_RETAINED`。aggregate 170.038666752 CPU s 触发 180−10 reserve 工作门；child −9，已记录自身进程组清理，无残留。
- 两臂终态、各 44,355 个完整 lifecycle events、输出/control/十字段/频次的留存文件独审相等，89 artifacts、1,147 config/freeze/prefix records、234,624 field cells、67 code hashes 已审；但 **没有最终独立 reference/RESULT，精确 kill 阶段未知**。源码/失败闭环审核 PASS 不能冒称整体数值 PASS。
- owner CPU 56.895277342→37.679090194 仅一次 fixed-order stage 诊断；候选包含 selective-LINE + identity cache，非隔离 cache 收益，不是稳定加速/采用结论。其余 72.770680806 CPU s 不能归为 reference-only。
- sampled combined RSS 高水位 284,516,352 bytes 不是连续峰值；最终父 RSS、reaped child maxrss 不是同一指标。逐进程 AS 与采样 RSS 不是硬聚合内存上限。原 namespace/Cython `FAIL_MODULE_IDENTITY` ledgers 保留，资格化不重写原始结果。

r2/r3 source manifests 可分别重建 30/31 文件（含候选源码 pin 元数据）；包装只做字节复制与路径/hash工具测试，未重跑目标/native/原 mocks。后续 terminal-only reference 恢复只有准备，本包不包含其通过成果。full M128 CPU FAIL / INCOMPLETE、历史数值失败、任务状态和 RTL/利用率未验收边界均不升级。
