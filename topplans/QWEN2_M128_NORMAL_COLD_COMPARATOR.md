# M128 正常加载与比较器增量

已完成：一次真实normal cold有限绑定；比较器R2源码与mock独审。默认关闭，不运行完整DUT，旧M16 DUT不声明PASS。完整说明和原件身份见 [候选README](../candidates/qwen2_m128_normal_cold_comparator/README_ZH.md)。

下一步在独立新profile完成真实终态guard、ACK/done、全部stream事件及非物化协议证据、输入/provider/ELF/官方oracle绑定，预算和exactreview后才能考虑一次完整DUT。oracle数值仅terminal后读取，不用参考填实际缺口。旧阈值与官方配置不改，固定4096 MAC及legacy PV63.57%上界继续保留，未达到80/90%验收。

历史FAIL和测试启动失败不改写；本小批发布源码/有限加载证据，不授权重跑或复用一次性账本。

当前实际RoPE provider容量1024，canonical/active128，inactive128..1023为零，shape[2,1024,64]；math.pow/cos/sin double后FP32存储。256仅旧参考诊断标签，官方32768不改。前版隐私漏扫安装绝对路径已在远端写入前被拒；r4无损逻辑投影保留所有736独立pins与历史拒绝，仅metadata/docs更正，代码/测试/数值不重跑。

扩展隐私复核另省略两项原Python对象地址及10项重复allocation地址元数据，不推断后者地址类型；公开逻辑角色、shape、bytes与hash保留，私有原manifest及原review身份不变。旧r3独审阻断亦保留，不能继承其publication GO。
