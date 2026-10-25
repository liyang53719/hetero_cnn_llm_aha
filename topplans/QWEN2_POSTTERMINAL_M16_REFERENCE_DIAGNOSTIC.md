# M16 Attention：独立参考恢复闭环，不改原失败

[源码、投影证据与完整边界](../candidates/qwen2_postterminal_reference_diagnostic/README.md)

- 新的 reference-only 进程退出 0，未重跑 DUT。两个原存档臂各 24,576 个输出 word、1,632 个因果 score word、十字段值/存在性与独立组件 recipe bit-exact；独审检查 351,936 个字段单元。
- 各自频次契约通过，但不可声称频次相同：DUT normalizer 为 1，参考为 `8*(token+1)`。
- 仅补齐已保存 **M16 Attention 组件**的独立参考数值闭环。原 r3 仍 `FAILED_RETAINED`、原 RESULT 缺失、原精确 kill 阶段未知；生产 r2 失败、恢复 r1 loader 阻塞与 r2 的窄 `PermissionError` 修复均保留。
- 新任务实际 43.305812158 CPU 秒 / 43.317565786 wall 秒；独立预算 180 CPU / 240 wall 秒，不是扩大原失败任务预算。八个持久化阶段齐全；46 个新 artifact、89 个旧 artifact 独审再哈希不变。
- 332,771,328 bytes 为离散采样的父进程加活动子树 RSS high-water，不是连续峰值。独立 reaped-child maxrss 与父进程终态 RSS 不得混作总树峰值。
- 隔离结论基于精确源码/数据流、阶段顺序、guard 和运行时资格；不是逐次 open 系统调用日志，也不是恶意 Python 沙箱。参考仍共享 exact 原语；不是官方完整层、完整 block、M128、RTL、周期/利用率或性能采纳验收。
- **原 M128 CPU FAIL、历史 bf16/fp32 FAIL、中文主清单状态与最终目标均不变。** 本批仅新增源码、角色化 pins、摘要及 hash 元数据，无原始 tensor/权重/header/字段/事件或私有运行配置。
