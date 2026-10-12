# Qwen2 QKV 分块归约接回公开完整链

用户于2026-10-12 10:50:23 UTC选择冻结官方BF16舍入和中间精度为目标。原逐节点 max_abs≤0.03125、mean_abs≤0.005 以及末输出 max_abs≤0.05、mean_abs≤0.01 均不变；FP32是诊断。Q21.3/U00.2仍ongoing，Q22/Q23/U01未关闭，五个block的M128总体验收尚未通过。

## 已定位的差异与目标

旧完整cold M128公开21命令到达终态，但官方causal scores/logits有11差、最大8。实际n0/K与官方相同；完整形状同实际Q/K输入的官方QK重放与实际全部causal scores逐bit相同。差异来自Q投影，不能继续修改QK、RMS、scale或mask。全部40个不同QR位置中，精确点积再舍入也仅27个匹配官方，不能靠提高精度冒充backend相同。

固定Torch2.10 CPU、oneDNN3.7.1、AVX512 core BF16、4线程下，通用两段独立FP32 partial与成对high-first顺序，在六组完整形状M16/M128 Q/K/V上全部逐bit匹配。K1536本profile选择1024+512；内部接口仍携带明确even范围与完整K/N stride，不把1024写成所有模型规则。JIT源指令/循环检查与数值证据分别保存，不能将静态代码位置当动态调用计数。普通数域结论不覆盖native FTZ/DAZ差异，旧IEEE渐进下溢规则未改。

官方与原独立BF16 producer在23个causal位置相距超过两倍0.03125；例如同一位置官方-856、独立-848，不可能同时满足这两个max门。用户选择的官方目标仍按原阈值验收；独立producer保留身份、差异和旧FAIL为辅助，不能为了双PASS暗改数值，也不能忽略官方原11差。

## 实际接入与资源

现有公开Command128/descriptor程序不变。Q/K/V Dense从真实RMS写回读A，完整A只装入既有bank一次，两个partial用同一Matrix资源写slot0/1；共享原16-lane Vector执行FP32 Add至slot2；原drain用真实DDR descriptor/data/ACK写回。完整N窗口结束、A lease失效且所有在飞退休后才给原Host终态。原Bias再从公开物理输出读取，并执行BF16物化。O/FFN/Down不采用这个QKV profile。

保持原A=688KiB、B=80KiB。M128/K1536的A在bank中为384KiB BF16，三份M128/N160 partial槽共240KiB；DDR的FP32容器大小不得误计为驻留精度。每16元素Add为两个逻辑64B读、一个写，原512B bank-word RMW实际为三个读和一个写。寄存器增量单列：K策略66bit、Vector模式1bit、Dense-drain admission 0bit；sum bridge599bit（含512bit lhs），coordinator1312bit metadata，集成wrapper4bit在飞义务。没有新SRAM、浮点阵列或固定MAC分母扩容；未证明PPA免费。

前端编译/CHIRRTL覆盖真实同bank owner、coordinator、sum bridge和Vector。相关参数默认关闭，未声称生产Host Chisel已启用或RTL数值通过。模型tick和主机秒数不计作硬件周期/利用率。

## 本轮验真边界

- 三组实际M16×32的Q/K/V窗口通过：原始真实权重与n0→实际Matrix partial→同bank Add→DDR/最终ACK，共1536个FP32输出逐bit一致；使用新的ProfiledMatrixService与每case计数差分，未注入partial参考。
- 公开Norm→完整M16 Q→Bias小链通过：24576个Q值，10个N窗口/20个partial；末ACK延迟五拍、Host尚未接受时不得发布，后继Bias读取真实公开输出。曾发现两槽Matrix result队列缺credit，修复后通过；该小链不是完整21命令。
- 独立新M16 C++ reference完整运行4.430秒，编译1.370秒；28个比较字段中所有适用原阈值的字段通过，QKV/Q/K/scores/logits逐bit匹配，y max0.00390625、mean1.407166322e-5。它不证明实际新链。原四源码和三回执已按原字节保留；冷打包改动后仅再生同SHA源码，没有重跑reference。
- 独立审查发现公开驱动在abort后未通知Matrix且过早抛错的真实缺口，现已修复：真实service abort、实际Done-ready及已接收DMA/Vector排空后唯一失败终态。定向覆盖接受read、Matrix step、result queue、DDR descriptor和Vector Add后abort，以及真实FP溢出；负返回码只锁存错误，不虚构result packet。
- 新M16第一次实际运行47.51秒，在pc13 O写回因同源Python模块重复加载的WriteBeat类型身份失败。实际数据形状正确，但隐式mask未被原物理内存接口接受；修复改为显式完整64B typed beat，原mask/last/extent拒绝门不放宽。失败前n0/QKV/Q/K全部与官方逐bit一致，已执行1632个causal scores/logits也逐bit一致；这只是失败运行的因果诊断，不是整块通过。
- 第二次M16实际运行68.91秒，O、残差、postNorm完成，首个FFN Gate窗口在旧A fence计数断言失败。现统一公开驱动的原始模块/type身份；新K-window A装载fence与旧FFN window计数分别记录，并提供累积总和，不在命令切换时清零。同实例QKV→O→Gate/Up/Down模式串联小门已通过：QKV/O各K=N32，FFN的56个局部N160窗真实写满N8960 Activation，再由Down K8960/N32读取并完成3次prefix/seed。27008 accepted Matrix steps、110624768执行FMA、新/旧fence=3/1，全程无owner或Matrix重置。最终11.588秒；这是内部真实端口模式小门，未代替公开21命令模型验收。第三次M16已冻结新身份后执行。两次FAILED及其源码/日志/失败capture全部保留。
- 第三次完整cold M16已通过，原进程499.32秒EXIT0；模型终态498.28秒，比较完成498.47秒。21命令/17 owner/1 Host result、17个公开输出共1,671,168B全部ACK；114执行源码与冻结副本一致。15个实际主阶段与6项内部节点对新固定配方逐bit一致，官方27个已分配门全部通过；Y max_abs=0.00390625、mean_abs=1.407166322e-5。原官方QKV与1632个causal scores/logits均逐bit一致，独立审查完成。详见 [M16紧凑结果](../reports/execution/QWEN2_DENSE_BLOCK_REDUCTION_20261012/M16_RESULT.json)。
- 此时旧执行层的native_acceptance仍是历史占位，不能据它判断当前数值；外层和comparison.methods是已完成的数值裁决，原receipt不重写。28个观测/输入节点中softmax_fp32没有批准容差，仅诊断；显式mask缺失，四个Attention张量各1440个future位置不执行，完整29节点仍未验收。
- 同冻结M128于15:16:20 UTC启动一次1800秒软件模型门；97.07秒完成真实prefix，尚未到完整数值终态。独立M128配方已在35.39秒完成：QKV和全部causal scores/logits逐bit匹配官方，所有已分配causal门通过；全unmasked scores另有4个未执行future位置最大差16，保留该FAIL，不能填充实际观测或声称29节点全通过。旧完整M128 FAIL、1200秒预算FAIL和独立producer FAIL保留。没有新增RTL或性能微优化。

新runner只在实际终态和完整ACK后打开对照；逐个主阶段与内部实际观测比较。官方FAIL给独立失败状态和非零退出，固定recipe一致另列。显式mask tensor未物化，未来causal位置保持缺失，不能把已观测项通过写成完整29节点通过。

## 远端验收及小型 CI 修复

实现已发布 [a2e4bee](https://github.com/liyang53719/hetero_cnn_llm_aha/commit/a2e4beef6ec5278a68a6bc4021780ff0f26aff8d)，63个Git blob和tree已逐项复核。其payload门成功；model CI因浅克隆缺少不可变825caff基线而失败，原失败保留。现仅补精确fetch/probe，并将子suite失败尾部明确打印、完整日志始终保存；同a2e4的干净浅克隆、无历史work/alternates下，新鲜共享Matrix库及13个isolated suite共117 tests通过。新增M128包装/形状测试已包含，其中不重跑M128。

[原frontend run](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/38267504488)的job结论为cancelled，不能改写成CI成功。不过已上传工件SHA a51f5a052fcdb7d687e55e6f1c7f4c019c47d9c3611c6798f2af97e9ad819eeb，经下载复核，新门17命令全部exit0，16份新CHIRRTL完整且summary PASS，耗时118.02秒；全工件有159份FIR。该job原预算15分钟，实际setup/小测约169秒，完整前端约747秒，上传另13秒。后续仅将这一无RTL的job预算改为20分钟，保留所有命令与门禁，并用完整workflow body哈希保证无静默跳过。旧cancelled与工件内完成的证据分开记录；不据此宣称新CI已过。
