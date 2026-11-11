# 08:33 真实参考与共享执行闭包恢复：完整数值 INCOMPLETE

## 状态和范围
main18a114cf、CI42981459617 success已核。上轮1116项本地文件在，约9.3GiB可用内存、57GiB磁盘。本轮不重复启动旧Qwen2/L3 Host，不恢复未知会话，不用目录缺失推定终止，不继承丢失PASS。源码/输入/证据本地保留，生成权重不上传，未清理文件。

## Qwen2真实输入与M128参考新执行
在10月保留目录找到原raw13张量，共94,382,080B，重新逐项匹配原获取hash。按原BF16位扩FP32、embedding前128行和矩阵转置，x/gamma0/wq精确匹配原11月输入身份，不再称权重缺失。
新运行完整首RMS与Q Dense：M128/K1536/N1536，301,989,888 MAC、196,608个Q输出；Norm约8.91秒、Dense约1.66秒。Norm SHA ccf1e6c065c6bc4e90458194aeda7475149451ac73479a6781d2fd638bf631df，Q SHA 1e67553e3bbbd2c1118ad860a4669accbff3ead6dd403439d1cc3d0867e3e5d9，与原身份一致且本轮实际重算；另4坐标完整1536项Fraction顺序核验一致。
仅独立Python参考；Q在bias/RoPE之前，不是21-op、Chisel或RTL通过。随后继续恢复原RoPE表与Q/K/V阶段，详见后续完成项。

## 0.8B两层完整input Norm独立参考
L0/L3各128×1024输出，逐节点Fraction RNE审计新执行约6.4秒/层，每层mul393344、add145536；输出分别81c43918…9dcb1和9929ee10…12a。原hidden无法恢复，明确使用新测试输入并冻结新hash（不匹配旧pin）；新fixture不能替代旧head4 FAIL回归或继承旧L3 Norm硬件PASS。L0零history/state重建后匹配原记录hash；L3原Torch trig闭包仍缺，未用近似替代。硬件没有执行。

## 真实ICG工具、源码与native恢复
从官方Debian获得匹配原计划SHA的Verilator5.032包，不使用sudo或绕过拒绝；恢复固定上游tech_cells revision的真实tc_clk源码。真实RTL直接模型与C ABI在256观察点一致（含低电平透明、高电平保持及enable/test切换）；8次未eval析构、8并行handle、时钟顺序/重复高及非法输入保护通过。
这次不是测试替身，但仅ICG native；Matrix、iDMA及全部17联合仍待重建。未执行Host或checkpoint恢复。

## 同一个4096候选IR
复用已验154核心源码/classes，一次固定4096硬件elaboration生成CHIRRTL，94,922,128B，SHA62b8fcc474967933d6f284ffa631dade96afbe5f7822a3e9466b5c32738eae06，29.63秒exit0。所有profile共用这一硬件定义，仅运行配置不同，没有逐profile重elaboration。
原firtool1.62.1匹配既存hash，一次--ir-hw编译80.08秒exit0，输出39,752,238B，SHA87e42450afc2776a9eb9e769a5591bc828f675aa2a48eff054bf0049eeb32052。没有生成SV、运行Host或做数值验证。新候选源码/IR不同于旧冻结身份，不沿用旧RTL hash。
层次安装审计：1049模块定义、reachable17外部实例=8Matrix+8ICG+1iDMA，原Norm/Conv/RawPrep/Chunk/GatedNorm/Attention/Elementwise服务可达。只证明结构，不证明native body或完整数值。

## DONE / TODO
DONE：Qwen2真实M128首RMS/Q参考、0.8B新fixture两Norm、真实ICG、同一4096候选IR生成与编译。
TODO：其余21-op参考与原输入表、Matrix/iDMA和严格异常17native闭包，之后才恢复统一模型真实完整执行；未知旧任务处理决定仍待明确。五块完整128token数值0/5，最终同刺激RTL未通过，80/90%完整block利用率未实测。本轮实际工作不等于完整prefill通过。

HW IR库存实际有105 fatal、105 error及1 assert；与旧记录107不同，原因仍需逐项核对，不能继承旧严格异常执行资格或视作断言等价。生成中23条警告保留原日志。Vector32Bank是既有32 Add/Mul bank、单结果槽与raw16兼容链/Scalar DivSqrt_small，不代表用户要求的32-lane每周期共享通路方案已经实现或通过。

## 本轮继续完成Qwen2真实前10个算子
全部13张量已重新生成FP32绑定。原Qwen2冻结RoPE表使用Host double pow/cos/sin再转FP32，不是Torch；从允许源码包恢复原freeze_trig.cpp，当前编译器/libm身份与原manifest一致，重新生成并匹配原表hash，没有近似替代。
在新执行RMS/Q基础上继续Q bias/RoPE、K Dense/bias/RoPE、V Dense/bias和KV cache，完整M128前10/21算子均新运行并冻结阶段hash。仍仅Python独立参考，不是Chisel/RTL通过；后11算子及最终block参考还需重算。没有把原历史全21结果迁移成当前通过。
额外已运行QK完整阶段的新向量参考候选，输出匹配历史hash且4坐标完整K整数/Fraction复核，但新整合代码尚待独立审查，单列TEMP，不计入已审前10op范围，更不计DUT通过。未启动PV或任何Host。本轮IR/native/参考作业均有明确exit0终态，和未知旧Host身份分开记录。
