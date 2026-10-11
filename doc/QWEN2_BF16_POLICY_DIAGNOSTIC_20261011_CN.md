# Qwen2 官方 BF16 物化策略：模型诊断，尚未验收

策略名称为 `qwen2-official-bf16-materialization-v1-diagnostic`。
它是原始混合精度 recipe 之外的显式软件候选，始终返回
`DIAGNOSTIC_NOT_ACCEPTED` 和退出码 1。没有修改 Chisel、RTL、固定 Matrix
精度、物理资源或原数值门限；先前所有失败保持原结论。

## 为什么需要这个候选

固定官方 eager BF16 forward 与旧硬件 recipe 的物化节点不同。旧 recipe 的
Dense、RoPE、PV、残差等中间结果保留 FP32，直到后继 Matrix 输入才舍入。
官方 BF16 在这些张量输出处已舍入，RMSNorm 还会先把归一化值转回 BF16，
然后与 gamma 相乘。候选只在这些公开的 dtype 边界添加 BF16 RNE，保留
原有递增 K 的 BF16 乘数、FP32 FMA、bias 末加、QK 16 路归约和 exp 近似。

有一项合同差异必须单独保留：当前 v0 文本规定 RoPE 在 FP32 完成 pair
rotation 后舍入；冻结官方 BF16 则先分别物化两个 BF16 乘积，再相加。
候选按后者诊断，所以 `hardware_v0_conformant=false`。它不能直接替代
当前 v0 硬件参考。真正改变硬件数值合同前，需要明确策略及对应误差影响。

若后续接 Chisel，BF16 RNE 与内存打包必须区分。当前 Qwen2 的 A/D 是
FP32 容器，不能把 elementwise 的 `dstBf16` 当作纯舍入开关；该字段还会
改为紧密 16-bit 打包，影响 stride、地址、write mask 和 ACK 字节数。
保留容器的策略应明确为“RNE 后以 FP32 精确展开值写回”。

## 同一候选软件程序的真实结果

输入是同一固定 checkpoint 的 embedding 行，cold M16 为 token 0–15，
cold M128 为 token 0–127，全部前置输入只有原始 embedding、权重和常量。
所有阶段读取本候选前一步实际输出。M128 复用 M16 的同一 C++/ELF，
未生成 RTL。后续导入证据会同时检查原始输出与派生视图的哈希和逐位关系。

| 范围 | 对官方 BF16 的结果 | 完整结论 |
|---|---|---|
| M16，29 个节点及语义 | 全部 BF16 节点门通过；y max 0.00390625，mean 1.98893e-5，relative-L2 0.000580228 | 仅候选模型诊断通过；仍不符合当前 v0 RoPE 合同 |
| M128，29 个节点及语义 | 15 个主阶段和 y 门通过；y max 0.03125，mean 2.13437e-5，relative-L2 0.000748274 | scores 最大差 16、logits 最大差 8 超原门，完整节点门 FAIL |

M128 的独立 BF16 公式对照另有 scores/logits/prob/gate 失败，也原样保留。
原 mixed recipe 对 FP32 开发预算的失败没有被改成 PASS。末输出改善不能
覆盖内部 producer 失败，尤其不能把局部通过称为完整 block 通过。

29 个观测节点包含 20 个 C++ 实算输出和 9 个从自身张量、只读输入派生的
cache/GQA/布局等视图。后者验证软件数据关系，不证明硬件缓存和 DMA。
FP32 softmax 内部值单独记录，未套用 BF16 逐元素门；原 row-sum 约束
2e-5 保持。M16/M128 最大行和误差为 1.78814e-7 / 7.15256e-7。

## 剩余差异与原官方后端

masked future 的 score 最大差发生在 head6/query70/key75。此处 Q/K
逐位相同，数学点积非常靠近 BF16 中点；常见的 1/2/4/16 路 FP32 归约
都会丢失中点的微小偏移，而原 native 输出在另一侧。这个位置不被因果
Attention 使用，但原诊断数值仍保留。

有效 logits 最大差在 head9/query102/key2，最早可追至 Q 投影的一个
BF16 ULP：相同 inputNorm 下，候选/官方 Q 为 1.8515625 / 1.84375，
被 K 的 430 放大。将 bias 提前能修这个点，但破坏另一个原正确点，
没有依据选择这种局部顺序补丁。

使用原完整形状和已保存张量的短 profiler/verbose 观测，Q Linear 经
`aten::linear → addmm`，QK 经 `matmul → bmm`，均选择 oneDNN
`brg_matmul:avx512_core_bf16`，src/weight/dst 为 BF16；Linear 带 sum
post-op。两项完整输出逐位复现原回执。此证据确定了内核族和该次输入身份，
没有证明全部内部累加指令顺序，也不把复刻不透明 vendor 舍入作为架构目标。

补充的条件算子诊断使用候选自身 Q/K：同官方 BF16 matmul/scale 的 99,072
个有效因果 score 与候选全部逐位一致，只有 4 个 future score 不同。将相同
官方算子换入后，对纯官方原 Q/K 链仍有 11 个有效 score 差异。因此当前
有效 logits 的失败来自上游投影误差传播，不能误归因于 QK 算法。此诊断不
替换任何官方输入，也不把原全链 producer FAIL 改成 PASS。

完整源码、原始/迁移报告及算子观测见
[封存证据](../reports/execution/QWEN2_BF16_POLICY_DIAGNOSTIC_20261011/evidence/README.md)。

## 下一步

- 保持原完整节点失败与 v0 合同差异开放，分离误差传播和单算子归约诊断。
- 用明确、统一、可实现的精度策略确定模型目标，之后再接最小 Chisel 改动。
- 结合 [prefill 驻留与调度审计](QWEN2_PREFILL_RESIDENCY_AUDIT_20261011_CN.md)
  处理固定资源下的 Attention/Vector 映射；单独优化 Dense 无法达到 80%。
- 当前没有新 RTL、真实 M128 硬件周期或利用率测量；Q21.3/U00.2 继续 ongoing。
