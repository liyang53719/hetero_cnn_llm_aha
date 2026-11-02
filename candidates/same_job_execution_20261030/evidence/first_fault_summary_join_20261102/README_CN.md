# 完整 summary 联测：有限通过范围

一次受监督真实控制链联测已 native0/errors[]，cleanup 与日志 EOF 完整。C 真 pack/七文件/编译证据校验、N review、E budget/approval、retained真实数据重验、dut_evidence、required_acceptance 与 summary.project 均走实际代码，未mock验证门。

- 正例：VERIFIED_REAGGREGATED / PRESENT_VALID。
- 多余 P1 收据、缺文档：UNAVAILABLE，拒绝混入未选profile/缺权威文档。
- 畸形snapshot：闭执行结果保留，snapshot=MALFORMED。
- 四项 numerical_pass 全 false。身份、ELF、编译/运行收据均显式合成；没有执行DUT、模型、EDA，也没有重算数值参考。真实旧权重/参考的逐hash仅是输入完整性检查。

耗时15.7888秒，采样RSS63,766,528B，observed CPU14秒；采样不是连续峰值保证。采用RSS1GiB/AS8GiB/CPU60秒/wall90秒、旧未知owner5GiB+系统1GiB预留、2GiB单文件/12,037,043,872B聚合watch门；未降低原门。

仅覆盖 joint catalog ef955913…（874 source pins）。后续最终runtime catalog变化需重新审计关系，不能称新源码已实际通过本次联测。R1 self-catalog hash漂移失败已保留，R2仅修合成fixture ledger。此包仅含小摘要、可复现测试源和说明，无原始日志/权重/参考tensor/ELF。

复现测试需显式提供已审核repo/catalog SHA、original binding SHA、原七件payload和fresh output，并由独立supervisor限额运行；不得直接把测试里的synthetic authority用作生产准入。
