# 四profile输入推进：未宣称完整硬件PASS

- done：0.8B L0/L3真实payload仍在本地旧checkout的work/qwen35_layer{0,3}_payload，原加载器重验全部hash/shape/HTTP range receipt。L0 14tensor/43,111,008B；L3 11tensor/36,705,280B。revision 2fc06364715b967f1860aea9cf38778875588b17。旧smoke结果不迁移。
- done：新增load_real_gdn_parameters.py，严格pin并按原存储加载Conv BF16(6144,4)、A_log FP32(16)、dt_bias BF16(16)，不改dtype/舍入。2单测普通/-O通过，包含真实位型与单字节腐败拒绝。
- done：独立generate_real_fixture.py接入训练参数，M128/head0原Conv→RawPrep→两chunk参考刺激生成成功；Dense QKV/AB仍合成，绝非训练完整block通过。未启动任何硬件数值测试；未碰并行Conv原作业。
- ongoing：L3真实权重已恢复，可接common runtime真实Dense→QKNorm/Rope/KV/GQA链。当前本轮尚未添加其硬件数值测试。
- todo：35B L0/L3未找到本地真实payload，官方header已重验，完整需求分别18tensor/1,685,402,304B及15tensor/1,672,492,032B。35B_REQUIRED_RANGES仅合法范围/shape元数据，不是下载/权重hash通过。没有截断MoE专家，也未按profile重elaboration。

所有五块完整M128仍0/5。本目录生成inputs/expected.tsv和decay.txt仅本地，不提交、不上传。未改生产DUT、下溢策略或MoE路由契约；未清理文件。
