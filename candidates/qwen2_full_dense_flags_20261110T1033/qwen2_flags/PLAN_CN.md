# Qwen2 M128七Dense全量值/异常flags审计（参考层，非硬件）

## done
新增有限BF16×BF16＋FP32域值等价证明、FP64 TwoSum精确残差审计；不再仅以FP64和与输出比较推断inexact。实际七Dense全部5,989,466,112个有序FMA、2,949,120输出逐字吻合上一轮M128结果；所有实际flags只有0/1，没有UF/OF。每个源输入/权重/结果SHA核验，RESULT列出。

原session8394 exit0/46.41s先执行全范围，后为补充rounding检查及残差operand证据，用原相同输入一次复测session61837 exit0/49.70s，结果与原统计一致。新脚本开始/结束均检查glibc fegetround=FE_TONEAREST(0)，只检查不修改fenv。600s wall/590s CPU/2GiBAS上限，未重跑完整SFU/21阶段。两次日志保留。

共31个实际FP64和非零残差。首实际例保存在FIRST_ACTUAL_RESIDUAL：Q token35/col816/K1020，a=3aa30000 b=32720000 c=c10d892b，输出c10d892b，精确NX=1，残差-2^-50，整数oracle及Fraction复核。**本真实全范围未找到旧FP64比较漏NX的实例**，这31例旧比较本来也是NX；不能虚报修正了实际漏报。新方法修复的是算法普遍缺口：例如BF16的2^-50×2^-50+FP32的1，FP64和已等于1但精确NX必须1，该定向例及其他测试明确覆盖。

84,804个独立案例（全部有限BF16指数对、随机尾数/符号、定向subnormal/overflow/zero等），新值/flags与独立整数oracle一致；TwoSum和+残差逐例与Fraction精确相等。普通和-O通过，所有断言均显式异常，不因-O消失。

## 精确范围
七Dense只有Q/K/V/O/gate/up/down，原K升序与每步FP32 RNE保持；无BLAS/归约重排、无FMA/精度政策变更。证明仅有限乘数和有限累加器，非NaN/Inf全IEEE域；数学证明与实际数据覆盖及硬件资格分开。

## todo / INCOMPLETE
QK/PV、全部标量与格式转换flags仍未全量覆盖；原Chisel/HardFloat实际结果/flags未比对。因此不是整个block flags资格，更不是同4096硬件/RTL数值通过。完整五块仍0/5，原head4 fatal FAIL不变。没有周期/有效MAC利用率测量。包只含源码/摘要/pin/hash，不含输入或生成数组。

父任务独立review报告额外30,846个指数差27/28/29/30的value/flags案例一致；这是独立审阅报告，不计入本脚本84,804的计数。RNE之外要求gradual-underflow，fegetround不单独验证FTZ/DAZ；本机次正规边界实测覆盖，不声称机器形式证明或输入BF16转换flags资格。
