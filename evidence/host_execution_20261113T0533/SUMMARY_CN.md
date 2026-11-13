# 05:33 原prefill首算子输入贯通及执行瓶颈修复（完整数值INCOMPLETE）

核main85f95041，CI43366693929 success仅payload；现场保留、工作树干净、临时清单已核，清理0。核原32597后续完整编译链均exit0，新profile0候选真实合法取指及无效opcode拒绝35周期通过；不继承旧硬件数值PASS。

本轮77342 exit0：同0433候选Host运行原Qwen2 M128的21命令/215描述符和FP32只读桥，439周期读15个AXI beat，其中原x的4×64B；issuedJobs1、pc0、resetRequired0。未写回/未完成首RMS，更未完整block。没有预载中间参考。

实际修复driver失败边界：原高相失败后read/drive仍可访问旧state；独立候选失败/关闭后拒绝读写，只完整周期成功才返回commit_sequence。真实Host+17库非法高clock注入验证无外部commit/旧值不可读，12cycle正常新旧输出与settle次数一致；非算术fatal验证。完整memcmp候选保持全state及17路比较，不删状态。

真实输入读间隔均94cycle/64B，仅M128首遍x外推约1155072cycle，非完整周期实测。精确512cycle reset/idle计时init0.140s、循环6.655s，eval4.911s(73.8%)、observe0.717s(10.8%)；不是活跃算子吞吐/RTL周期/有效MAC利用率。未因120秒预算重复首RMS冷前缀。定位现机器码为llc-O0，唯一98883已启动同冻结LLVM的-O1候选，2CPU/300秒、无fastmath、保原对象；尚未经差分不能替换或报提速。

更正前轮缺源判断：QwenOwnerKernel实际在QwenOwnerProtocol.scala，非同名文件。审确认1/2独立runtime FFN、3/4真实MoE路由与共享算术；Dense五tile为循环缓存而非M≤80。LegacyV0不覆盖runtime明确BF16存取。1/2严格安装契约候选另一路并行推进，未删除guard或称已准入；35B完整权重仍缺。

五块128完整原Chisel仍0/5，最终同刺激RTL和4096完整block有效MAC80/90%未测。原L0 head4 FAIL、MoE同分契约及旧未知Host不重启边界保持。只发布允许摘要/hash，源码/数据/必要证据留本地。
