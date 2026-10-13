# 35B exp 渐进下溢软件候选（2026-10-13）

## 范围与未闭合项

本批新增显式 DecayScalar.exp_negative_ieee_rne：P7 近似、多段 ln2 range reduction、
逐节点 FP32 RNE 与渐进下溢。保留默认禁用和旧 exp_negative/op4 的绝对值80零截断行为。
生产 BlockFloat opcode5 仍不支持，本批没有 Chisel opcode 绑定、实际 Prep 接线或新 chunk 执行。
这是 IEEE 数值范围/渐进下溢支持，不是全域正确舍入 exp，也不声称 Torch bitexact。
没有新增数值验收阈值；所有本批误差结果 passed/thresholds 都为 null。

一个继承 PrepScalar 的实例，使用既有 P7 系数；中心整数 k 使用 RNE，split ln2 高低部降低
range reduction 误差。k>126 时先做正常数缩放，末次乘最小正常数才允许渐进下溢。
输入绝对值≥104 的零 guard 位于半最小 subnormal 边界之外；有限非正输入保留原值，
非有限/正输入拒绝。启用时验证 FE_TONEAREST 与 subnormal 输入/输出行为。
固定边界包括 c2cff1b4→00000001、c2cff1b5→00000000；边界见证不是全域证明。

## 实际输入上的单算子诊断

读取已发布 4f990678 的实际 M16/M128 Prep 原始 g，验证原 summary、71执行源、10 native、
raw SHA 后做单算子重放。没有把旧 raw 导入新 TypedMemory 生产者。
参考实际为固定 Torch 2.10.0+cpu DEFAULT、单 CPU/线程的 torch.exp；每组形状记录在摘要。
原运行 report.official_source 是 RMS/model 上游来源，不能当 exp kernel/AST 身份。
官方 chunk exp 调用见 pinned modeling_qwen3_5_moe.py 339/344/371–373/441行。
候选 chunk exp 输入由当前候选 ascending FP32 cumsum 构造，不代表运行官方完整 chunk。

|输入组|元素数|新候选差异数|最大ULP|旧实现错误置零数|新错误置零数|
|---|---:|---:|---:|---:|---:|
|[-104,0] FP32网格|10001|951|1|2305|0|
|M16实际g|512|17|1|16|0|
|M16候选chunk指数输入|70688|828|1|193|0|
|M128实际g|4096|120|1|128|0|
|M128候选chunk指数输入|141376|4361|1|918|0|

网格保留9050个0ULP与951个1ULP的完整分布；所有输入/输出 raw 的字节数与SHA在机器摘要。
实际 head22 g=c2b72752 对应新 exp=0001d7fd，避免旧实现直接归零。
五组≤1ULP是本次固定样本观察，不是新验收门或正确舍入保证。

## 资源与计数

新旧各226673次 Scalar compound 请求，共453346；同一 Scalar identity。
新内部 mul=2419351、add=1812546、integer_rne=201394、零 guard=25279。
普通缩放路径12 Mul+9 Add+1整数舍入；subnormal路径13 Mul+9 Add+1整数舍入。
这些是软件内部节点计数，没有映射硬件时钟；本批 Matrix/Vector MAC执行均0。
完整block周期、占空比、有效MAC利用率未知，不用27.466秒主机运行时间推算硬件性能。

## 尚未修复的独立数值差异

- 同 raw 候选 ascending FP32 cumsum 与固定 Torch 的 M16/M128 输出仍有1001/2356处差异。
  样本中 FP64 累加后转FP32吻合，只是观察，未据此声称所有Torch后端都使用FP64或增加硬件资源。
- Q/K 同raw重放显示 square逐元素精确，128元素sum顺序为首个差异；替换该sum为固定Torch观察值后，
  当前剩余链输出全部吻合。这只定位原因，当前实际Prep仍保留原Q/K诊断差异。
- g 的 exp(A_log) 与 Softplus7 都有误差来源。新exp32加原Softplus7的局部重放使M128最大绝对误差
  从5.340576172e-5降到1.52587890625e-5，但最大ULP由35退化到37，不能只报改善或标PASS。

## 验证与下一步

新增8项小测通过；全量冷门521项/46套/145源，零skip，前后源码不变。
指定计划/清单 pytest 91项通过；初次误用 unittest 未发现测试，不计通过。
独立审查重算五组raw、输入身份、分布、渐进下溢及计数。原始运行摘要不覆盖。
先完成本批发布和精确CI；随后按固定官方实际归约规则选择最小接线更改。
32头stride、cumsum、Prep Q/K归约、Softplus g分别推进，不一次混改。
完整35B block、warm state原子提交、RTL与80%/90%利用率目标继续open。
