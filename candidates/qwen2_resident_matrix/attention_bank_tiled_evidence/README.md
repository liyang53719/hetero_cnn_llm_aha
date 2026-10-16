# 已执行：真实单作业 M17 / M32 分块 Attention

- 已完成：M17、M32各一次，原始owner Fraction oracle与同一A Banks候选逐位比较全部score和output，通过。
- 已完成：候选代码独立审查；12+12冷测试，77+7源检查。执行源 pins 为 c7aaf3c5d0dbc2923846059e0661bba0434c20ee2f4351f7044a19b170e6b24c。
- 已完成：独立核验实际receipt、全部源身份和执行pins；2+2证据测试使用原始文件通过，零跳过。
- 待办：明确预算批准后运行M128。当前M128未执行。

M17 receipt wall15.249759s（CLI15.421251s），reference9.138362s，candidate6.076308s，CPU15.224345s，峰值RSS37012KiB。Matrix2034步骤/250结果ACK；scratch12852事务/38558边沿；验证26,112输出word和1,836分数。

M32 receipt wall53.329775s（CLI53.515920s），reference32.408390s，candidate20.860754s，CPU53.313606s，峰值RSS43232KiB。Matrix5664步骤/640结果ACK；scratch44352事务/133058边沿；验证49,152输出word和6,336分数。所有请求/返回/ACK余额与静态公式相符。

M17内部25s/外部30s，M32内部75s/外部80s。两次执行均使用冻结同一源身份，正常退出；EVIDENCE.json保存原始安全JSON精确文本和SHA256，没有tensor/权重。hypothetical_ticks只是假定捕获/除法时序模型；host Q/K/V和最终输出物理供数仍未放置。不是RTL或完整block的性能/数值结论。

M32按因果对数99,072/6,336外推M128约834s。内部1200s/外部1210s只是下一次单次执行预算提案，不构成成功保证或已获准执行。

核验命令（提供原始安全receipt目录时不跳过文件核验）：

    BANK_TILED_RECEIPTS=/path/to/receipts python3 -S -B -m unittest candidates.qwen2_resident_matrix.attention_bank_tiled_evidence.test_evidence -q

执行模块README记录的是冻结时准备状态，本文件记录后续真实执行结果；不能修改执行源身份以更新状态。
