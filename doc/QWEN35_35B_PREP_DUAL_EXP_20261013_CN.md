# 35B Prep g 双节点exp显式候选（2026-10-13）

## 变更范围

新增35b_finite_nonpositive_fp32_dual_p7_exp，仅GROUPED35B布局、启用三项开关的
同一个GateScalar可进入。RMS、QKV、Conv、A/B、ACK重排、Prep仍共享原物理模型资源。
外层exp(A_log)与Softplus内部exp(-abs(x))同时使用已发布的P7 split-ln2渐进下溢算法。
旧Softplus/opcode7、旧exp/opcode4和默认policy保留；新softplus操作没有生产opcode绑定。

DecayScalar原运算提取为内部_evaluate_exp，已验证/持有owner的compound复用同实例，
内层exp只增加内部节点计数，不伪造第二次外部请求。内部方法不是无所有权公开接口。
真实owner保持先biased→Softplus→外exp→正log时reciprocal→g，再原beta；
每token/head真实执行外exp，没有将32个A_log值缓存以偷减实际工作量。

## 同节点四消融

下表是先行独立host探针，最大绝对误差/平均绝对误差/最大ULP；不是实际owner计数。

|规模|old|仅外层|仅内层|同时替换|
|---|---|---|---|---|
|M16|4.959106e-5 / 2.040967e-6 / 33|1.525879e-5 / 6.673971e-7 / 33|6.484985e-5 / 2.422141e-6 / 17|7.629395e-6 / 3.556378e-7 / 4|
|M128|5.340576e-5 / 2.038089e-6 / 35|1.525879e-5 / 5.528803e-7 / 37|6.484985e-5 / 2.392776e-6 / 17|1.525879e-5 / 2.397552e-7 / 4|

仅外层M128最大ULP由35退化到37；仅内层虽降ULP，最大绝对误差反而增加。
两档Softplus最大ULP从43降为3；同时替换仍不是bitexact，不设新的容差或PASS门。
探针574个节点raw/hash留在work，Git只存复现源码与摘要，原权重/激活不入Git。

## 残差归因

- 新内exp对辅助Torch exp(-abs(x))仍可能差1ULP。
- 同候选e，原FP32系数用FP64计算完整log系列后一次转FP32，与FP64 log1p(e)一次转FP32
  在两档全部相同；现逐节点FP32尾部仍最多3ULP。这里FP64只是诊断观察，没有加入硬件候选。
- Softplus点[5,9] x=-4.25：e为3c69b488，辅助exp为3c69b489；同e的log1p一次舍入
  为3c680dd8，逐节点尾部为3c680dd6，官方Softplus为3c680dd9；最终+0精确。
- M128点[41,22]两exp都与参考相同，log尾部亦等于log1p(e)一次舍入，但先舍入log再加正x
  得3fac82c2，log1p(e)+x一次舍入及官方为3fac82c1。残差包含中间值双舍入，不能全部归因exp。
- g最差点[7,27]仍有外exp、内exp、log尾部舍入共同贡献，最大4ULP继续是诊断。

## 精度与资源边界

Softplus保留x>20直接返回、x=20执行、x<=-80拒绝，finite/enable/ownership检查保留。
其余节点仍原FP32 RNE：e、2+e、e/(2+e)、平方、原系数Horner、2*y*h、最终加法。
外层先exp(-abs(A_log))，正号时再原FP32 div(1,e)；g仍原MulIeeeRne，beta不变。
没有裁剪原g、改BF16转换、增加FP64、第二Scalar、新矩阵阵列或DDR供数端口。

新内部节点严格串行；compound数、内部exp数、Mul/Add/Div分开报告，不能相加当成新增MAC容量。
新近似算法不是正确舍入exp，旧Q/K固定归约policy保持；未接生产Chisel，实际周期/占空比未知。

## 验证方式

小门覆盖旧op7数值不变、默认禁用、x=20/20.5/-80、非有限、所有权、内部exp不增public request；
实际owner覆盖policy错配、域错误后同owner reset重用、held-success abort不publish与计数隔离。
实际链按M16再M128用原冻结输入/权重重跑，不把旧中间raw导入伪producer；各输出与参考逐角色比较。
复现沿原candidates.qwen35_35b_prep.run入口，显式传：
--reduction-policy torch_2_10_cpu_default_f32_8lane_4ilp_128
--gate-policy 35b_finite_nonpositive_fp32_dual_p7_exp
并提供既有pin下载/转换脚本生成的payload、原N8192/N32参考报告及SHA，输出只选新work目录。
原上游strict门全部保留；g改善不等于Prep整体、chunk、完整block或RTL数值通过。

## 本次新实际生产者结果

两档各74执行Python源、10native前后不变，七真实终态；原输入、上游所有output SHA与
上一固定sum批一致，Q/K/V/beta及padding逐字节不变。实际g逐字节等于独立双替消融结果。
M16 g最大33→4ULP、maxabs7.62939453125e-6；M128最大35→4ULP、maxabs1.52587890625e-5。
原上游strict门继续通过；history仍未发布staging，4ULP仍只诊断。

真实Prep每档外exp/新Softplus/旧betaexp各512或4096个public request；内exp另计512或4096，
不是public request。M16新exp内部Mul12288/Add9216/integer_rne1024；M128为98304/73728/8192。
新Softplus尾部内部M16 Mul5120/Add4608/Div512，M128为40960/36864/4096。
Prep DDR M16读401408B/写819200B，M128读3211264B/写6553600B；transport ticks同旧。
固定Matrix4096/Vector16/Scalar1不变，Matrix每档执行2164260864 FMA；有效M16 270532608、
M128 2164260864。内部Scalar节点不是Matrix MAC；完整block周期与硬件占空比未知。

全冷门534项/49套/150源零skip，源码前后不变；指定计划/清单pytest91项通过。
