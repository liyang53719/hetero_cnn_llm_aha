# 默认关闭的 Attention raw scratch 源级扩展

已完成：三目标零fuzz补丁与冷行为测试。已完成：独立源评审及15+15冷测。待办：Scala/RTL编译仿真、kernel/Attention控制器接线、完整同激励验证。当前没有数值或EDA执行，也没有硬件性能结论。

## 地址与物理资源

原raw key本来就是13bit；默认仍仅允许line0..4095。显式enableAttentionScratch=true且enableRawKv=true时，额外允许4096..4191。银行映射完全复用原单读/写site：bank pair=2*(line%8),2*(line%8)+1；word=line>>3。因此96个64B line占用原16个A-bank的word512..523，共6KiB，没有新增payload SRAM。score为4096..4143，probability为4144..4191；plane是地址隐含值，不进入原4096个KV-valid bitmap或DDR KV地址解码。

## 上下文、ACK与排空

新增可选scratchBegin控制口沿原Dense owner raw端口透传，仅在同一真实exclusive lease且pending/held debt为空时接受owner/generation/query/KV-head。generation严格递增；release/soft reset不回退，达到32bit上限必须走系统级冷恢复。请求key与匹配ACK附带generation32/query7/head1；低区raw请求这些字段必须为零。默认关闭时这些字段和控制口不存在。

scratchWritten独立96bit；先写后读，仅matching clean ACK发布written位。物理SRAM写仍发生在原request接受边沿，abort不能回滚字节，但会撤销有效性。begin、acquire、release和abort/reset使scratch有效性失效。请求需要active context；已接受请求的ACK即使abort使active失效，仍按保留的generation/query/head与完整held key匹配来排空。新begin/lease不能跨过pending或held debt；foreign或跨generation的stale ACK不能退休当前请求。同一generation/query/head上下文内，调用者必须保证：只要旧ACK仍可能延迟或重复到达，就不得复用transaction tag。完整held key相等无法区分复用相同key后的旧ACK重放；本扩展继承此调用者前提，没有新增tag历史寄存器。

每次交易：request edge0访问两个256bit banks；edge1形成现有512bit held response；最早edge2匹配ACK；下一请求最早edge3。ACK不访问SRAM。没有六头并行读、隐藏line cache或免费port。raw parent仍从真实Dense/DMA/Matrix/seed/response债务导出准入；本补丁不绕过parentDrained。

## 增量寄存器账本

scratch context generation32/query7/head1/active1=41bits；written96bits；原held RawKvKey增加40bits，合计177控制bits。没有新增payload寄存器；原512bit response和SRAM保持。输入/output wires、比较器、动态bit-select和UIntToOH逻辑不是零成本，但尚未综合。旧owner/tag/poison/pending/held计数不重复计为增量。

## 兼容与缺口

这是新可选ABI，必须由后续调用者显式构造扩展key并绑定真实query/KV-head/generation。现有Packed client、Python完整Public、kernel和原owner默认路径均未接入。冷模型复用调用者同一个Banks对象，保留raw bits，包括NaN/Inf位型；没有浮点解释。源组合仅使用原raw_kv_parent已钉住的三目标闭包，再应用本补丁；不把三文件组合误称为完整可编译工程。

测试：python -m unittest candidates.qwen2_resident_matrix.attention_raw_scratch.test_model candidates.qwen2_resident_matrix.attention_raw_scratch.test_sources；再使用python -O运行。禁止把这些冷测当作RTL PASS。
