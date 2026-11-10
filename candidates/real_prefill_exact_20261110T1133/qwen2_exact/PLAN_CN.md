# Qwen2真实M128剩余数值链数学审计（TEMP）

## 本轮实际范围
复用SHA核验后的真实完整21-op参考中间数组，不重跑七Dense。QK保持12query/2KV heads、HD128，每lane8次FMA，再lane0..15独立FP32加法折叠及独立scale；PV按key递增，只覆盖原causal允许键。完整QK与PV各12,681,216次有限BF16乘数FMA的值/flags均审计，QK另1,585,152 add和99,072 scale mul。所有存储score和attention输出逐字吻合。

完整softmax执行原degree7系数与每节点FP32舍入，按原key顺序sum、每行Fraction精确1/sum、末FP32 multiply，全部保存prob逐字吻合。原Qwen2契约只遍历causal允许键，不借用Qwen3.5的minfinite mask分支。compound_exp内部node flags仅诊断，不编造原聚合error/flags。

两完整RMS按原Qwen2逐元素ascending square/sum（不是Qwen3.5的32lane分组），全部normalize/gamma节点及256个Fraction精确sqrt/div对审计，两个最终BF16输出逐字吻合。完整SiLU按原六阶段FP32顺序，每个实际distinct denominator独立Fraction精确倒数并复用其精确字，非FP64近似除法；1,146,880最终act值吻合。全部bias/RoPE/residual FP32节点及两KV拷贝亦逐字核验。

## 数学依据与独立核验
FMA沿用已审有限BF16×BF16+FP32的FP64中间值等价和TwoSum残差证明（依赖pin列出）。普通FP32乘法最多48有效位，binary64可精确容纳；FP32加法两24位数在指数差<=28时精确和<=53位，大差时dominant本身FP32可表示且小项不能跨FP32边界，TwoSum恢复NX残差。取tiny-after且NX为UF，OF|NX用于溢出。每个脚本要求RNE并实测FP32最小subnormal加/乘不被FTZ/DAZ冲掉，执行末复核。

独立整数/Fraction核对4个真实QK和4个PV坐标的全部归约（833 FMA）、5,568个有限FP32加/乘及flags，普通/-O通过。所有运行的实际flags仅0/1，未检测UF/OF。源码不调用BLAS/matmul，不重排归约。

## 明确未完成
这些是数学参考值及节点flags审计，不是原Chisel执行或RTL通过；不包括输入BF16量化flags/所有format硬件聚合状态。部分运算用已论证binary64数值路径而非每一步Fraction，精确测试不能代替硬件比较。原硬件head4 FAIL不变，五块完整原Chisel/同RTL仍0/5，未测利用率。所有输入/数组留本地，只提交源码/pin/hash/摘要。
