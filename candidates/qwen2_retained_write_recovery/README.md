# Down 写描述符的已退休债务判定

本次新增独立 sibling，不修改已发布计算链，也不清除 owner.accepted_write。

问题：原统计把 accepted_write 非空等同于未完成写。原 owner 在成功 ACK 与终态退休后可保留历史描述符，因此仅看指针会误报。

修复仅在以下条件全部成立时，把该项债务判为已退休：owner/writer idle、无错误、无 command/data/ack_ready、无 owner/physical pending；描述符落在唯一 Down allocation；整片 Down 写与 ACK 地址精确全覆盖；存在唯一完全相等描述符对应的成功 ACK，tag、bytes 完全匹配。其他债务原样保留。缺失或异常证据拒绝放行。

测试范围分两层：

- test_debts.py 的 8 项测试使用 transposed_seed 基础 DenseOwnerModel、真实 PhysicalMemory 与原 wire 类型，128 字节合成数据。该基础 owner 不是公开 runner 的 FfnDrainOwnerModel 继承链；其中 held-terminal 测试直接初始化 finish/ack，属于隔离判定测试。
- test_ffn_drain_debts.py 使用 execution.numeric.model 实际加载的 FfnDrainOwnerModel（FFN 三开关开启）及其 Down wire、真实 PhysicalMemory。2048 字节、16 个 burst 的零载荷写入与 ACK 走真实 writer；owner 从人为初始化的最终行 execute/ack 边界，经最后 ACK、finish 保持 3 拍、response_fire 到 idle。覆盖欠 ACK、错 tag/error/bytes、先前 burst 缺写入或 ACK、descriptor 不变及其他债务逐项不变。

以上均为轻量协议边界测试，不执行 Matrix 数学、完整 job launch、M128/K8960 调度、Host 公共终态或 RTL，不是完整模型验收。独立债务适配入口为 debts(x, physical, memory)，需未来 runner 明确接入并重新冻结，不通过猴子补丁修改原运行。

复核命令：

```sh
PYTHONDONTWRITEBYTECODE=1 python -m unittest candidates.qwen2_retained_write_recovery.test_debts candidates.qwen2_retained_write_recovery.test_ffn_drain_debts -v
```

## 中文小批计划

- done：新增严格 retained_write_evidence / corrected_debts 与正负协议测试。
- ongoing：独立审查、复跑冷测试、独立提交源码。
- todo：恢复固定版本 PyTorch CPU 参考环境（当前 Python 3.12.14，torch 缺失）；按已有 upstream pin/hash 按需重建原始输入与独立参考。
- todo：恢复新 runner 的显式债务适配、固定资源/阶段统计及有界监督，不继承失联 v2 或丢失候选的 PASS。
- todo：在上述身份与预算准入通过后，重新从输入开始同一条完整 M128 链；仍需实际完整 RTL 数值和 90% 利用率验收。

原 v2 的观测窗口已结束，原环境与会话失联，目前没有可接续运行身份。本小批不启动长计算，不上传张量或此前被拒的 metadata。
