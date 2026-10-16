# +384 B 面板：真实 M17 / M32 数值与银行事务证据

- 已完成：候选22+22冷测试与90+8源检查、独立代码审查。
- 已完成：一次M17、一次M32实际整作业；全部score/output逐位匹配原始owner Fraction oracle。保持原始每输出算术顺序和BF16边界。
- 已完成：原始receipt、源身份、完整输出散列及4G计数独立核验；2+2原始文件测试通过，零跳过。
- 待办：真正Public物理DDR/共享owner/native Matrix profile集成；当前不执行新面板M128或RTL。

执行pins7c0b2bd06bdcdc501c242a52e702f079c90ca72c35031510d95f7e1d27675431。候选执行源保持不变；其README为准备时状态，本文件记录后续结果。

M17 wall14.739614s（CLI14.933337s），参考9.307524s、候选5.382572s，CPU14.735649s，峰值RSS36744KiB。Matrix2034步骤/250ACK；bank432读+432写=864事务，2594边沿。

M32 wall54.449424s（CLI54.649557s），参考36.692010s、候选17.679760s，CPU54.389569s，峰值RSS43468KiB。Matrix5664步骤/640ACK；bank1152读+1152写=2304事务，6914边沿。相同shape旧7P策略44352事务；实际减少42048条。全部scalar/Matrix算术计数及输出值保持。

M17内部25s/外部30s；M32内部75s/外部80s，均一次退出0，无重试。两个receipt保存精确安全JSON与SHA，无tensor/权重。

panel显式记为新增384B；denseWeights物理retention未证明。Q/K/V和输出仍host-fed。divider_spacing3只是数值测试的假设，实际源码除法25/26下界必须另计。hypothetical_ticks与Pythonwall都不能视为硬件周期、利用率或完整block性能。

核验原始文件：

    BANK_PANEL_RECEIPTS=/path/to/receipts python3 -S -B -m unittest candidates.qwen2_resident_matrix.attention_bank_panel_evidence.test_evidence -q
