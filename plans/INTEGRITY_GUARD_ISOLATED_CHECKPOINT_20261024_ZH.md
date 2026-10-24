# 完整性检查临时对象优化：独立本地检查点

基线：1f5b1c203767f48345ce324685dba539eeee7a4f。
本检查点尚未集成或推送，不改变既有完整数值及 RTL 验收状态。

## done

- PASS：148/148 项有界冷态与合成测试通过，0 失败、0 跳过，36.712 秒。
- 覆盖：Scalar 绑定 15、exp admission 6、合成 legacy coordinator 控制 57、合成 experimental coordinator 控制 11、合成比较及 seal 38、backend admission 17、policy 4。
- 新增六个冷态测试；相同 15 个冷态测试分别对基线与优化实现执行，均 15/15 通过。这是额外执行次数，不是额外的不同用例。
- 生产改动仅将 Scalar identity 的闭包生成器换为显式循环，空闭包不构造 zip；绑定、代码、默认参数、闭包长度及 cell 检查顺序和错误优先级保持不变。
- full_driver 字节不变；检查时机、数学、row1 策略、FP flags、native backend 和数值门槛不变。
- 合成 coordinator 测试使用替代数值 owner 与零占位参数，验证 TypedMemory 写入、ACK、发布及提交控制，不是数值执行。
- 审计期间没有 native load、子进程或网络请求；没有 Scalar 数学、实际 Chunk transport、checkpoint/Torch、完整模型或 RTL 运行。
- 轻量 guard-only 微基准：每组 5 个样本，每样本 4000 次。DecayScalar 中位数 64.477 → 53.456 微秒；PrepScalar 50.050 → 43.089 微秒。分别减少约 17.09% 与 13.91%，不是完整运行瓶颈或端到端加速结论。

## ongoing

- 仅保留独立本地检查点供复核；冻结原工作树，不改动其 HEAD 或 Git 数据，不触碰既有运行进程。

## todo

- TEMP：full M128 数值执行结果仍未验证；不能从上述冷态及合成测试推导通过。
- TEMP：RTL 未验证，本次没有 RTL 执行或硬件性能结论。
- 先确认既有长跑的终止状态并解除冲突风险，再决定是否集成及开展后续验证。
- 本次未 push、未更新远端引用、未触发 CI。
