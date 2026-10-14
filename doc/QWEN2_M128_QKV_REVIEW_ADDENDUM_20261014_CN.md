# Qwen2 M128 QKV 独审状态追加勘误（2026-10-14）

8dd 提交中的原始 `SUMMARY.json` 保留了生成时的 `PENDING_INDEPENDENT_MODEL_REVIEW`。其后独审已经完成，结论为 `PASS_INDEPENDENT_M128_MODEL_AND_SOURCE_ONLY_PACKAGE_REVIEW`：104 项检查、145 项执行源身份及39项产物记录通过。原始执行摘要未覆盖、未回填为新的执行结果。

[追加审阅回执](../reports/execution/QWEN2_M128_QKV_REVIEW_ADDENDUM_20261014.json)记录原摘要与独审文件的完整 SHA-256。原独审文件未自带完成 UTC；本次读取的文件 mtime 是2026-10-14 10:59:06 UTC，但不能将文件时间当作经过认证的审核时间。本次追加记录的 `issued_utc` 是现在重新核验145源、39产物哈希均未变的明确时点；未重跑数值。

审核范围仍是 M128 public21 的 pc0..8 同链软件门：6 个官方 producer 节点逐字节一致，3 个 raw producer 对独立 typed recipe 逐字节一致。9 个 owner 终态、8 个 public completion 退休；pc8 held，V 尚未发布，Attention、finalfence、完整 block 及 RTL 均未在该次执行完成。软件 ticks 和计数不等于硬件周期或利用率。

该历史 QKV 独审不会使随后 [7975 的 Attention 预算失败](../candidates/qwen2_live_attention_model_m128/FAILURE.md)变为通过。后者未到 pc12 held、未进行官方 Attention 数值比较，仍保留未退休服务义务。
