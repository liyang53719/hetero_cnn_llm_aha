# 原始 HostControl M16 Job 类型衔接修复（进行中）

原始完整程序的 Attention 请求由 HostControl._admit_attention 生成，精确类型是 ffn_public.model.group.PrefixJob。独立小样本使用 prefix_owners.Job，两者字段相似但类型不同。第一次完整 M16 运行在 prefix 成功后、Attention job 接受前被严格类型门拒绝。

本独立组合版本只替换完整程序 profile 的一个 import 和一个精确类型判断。旧10b301入口、失败运行、独立M1/M2路径保持原字节。所有 owner/service 类型、idle、银行债务、源码、ELF与资产门保持不变；不增加 duck typing 或 subclass 接受。

测试通过原始 PublicFrontend/HostControl 的真实21事件元数据，接受前10个明确 CONTROL_ONLY 完成令牌，再取得真实 Attention PrefixJob。令牌不代表执行 prefix 算术；此前真实完整运行的 prefix 结果另行保存。修复检查不会运行 native 或完整程序。

已完成：3项 normal/-O 控制测试，复现旧类型拒绝、验证修复后通过类型/债务门，以及316源完整闭包。进行中：独立复审和更新启动器的固定源契约。待办：完整程序重试，仍需单独授权。

运行命令：python -m unittest candidates.qwen2_resident_matrix.attention_packed_m16_host_job.test_host_job -q，另用 python -O 重复。测试中的源码/ELF门使用抛出标记终止，不加载native；这不是完整 profile.install 或数值成功证据。
