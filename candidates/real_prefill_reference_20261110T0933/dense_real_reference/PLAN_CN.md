# 真实0.8B M128生产者数值连接（TEMP）

本轮实际运行两个profile，不串等完整block。L0已执行input_norm→QKV/Z/AB→Conv4→RawPrep全部128token/16head；L3执行input_norm→Q/K/V全部128token。输入是上一轮绑定的caller synthetic dyadic hidden，参数为已校验官方真实权重，不声称输入为官方embedding。每个源segment SHA/字节数重核。输出仅本地保存，不预装硬件中间内存。

原RMS按GdnRuntimeRmsNormOwnerV3的32向量lane映射（8CPU lane×4residue）、每512元素16term、分块累加、residue0..3折叠、lane0..7折叠；不能套旧ascending求和。normalize与(1+gamma)各FP32运算，最终BF16。第一真实行1024元素归约与独立Fraction逐节点精确对照通过；两项测试普通与-O通过。其余算术复用已有独立参考函数，未逐节点全面资格。

Dense复用有序K、BF16乘数/FP32累加候选，输出物化BF16；禁止matmul替代。Matrix/scalar flags均NOT_QUALIFIED，NumPy候选未全量Fraction对照。RawPrep是无token间状态的真实M128准备步骤，逐行Python实现不冒两个M1替chunk；本轮未执行chunk/recurrent、attention、后半FFN、Chisel或RTL。完整五block仍0/5，不报告有效MAC利用率。

运行session71039，timeout180s，exit0。工作集仅约几十MiB权重+中间数组，无重复下载/权重上传。现有原underflow FAIL不变。重现：在对应历史目录输入与依赖存在时运行run.py；所有生成bin仅本地，源码包排除。原文件不删除。

追加：真实Dense输出8个坐标（L0 QKV/AB、L3 Q/K各首尾坐标）每点全部K1024对独立Fraction FMA及BF16 RNE，0差异，只验证这些位值不含flags。L3继续执行原C2 QKnorm至qn/kn与Qgate分离，128token、Q8head/K2head，原BF16指数95..158准入已检查，尚未RoPE。

数值局限逐项：candidate.py以FP64乘加再转FP32模拟逐K FMA，非全域精确资格；RMS/QKnorm/RawPrep sqrt使用np.sqrt(dtype=float32)，Div使用np.divide(dtype=float32)，未独立逐节点全量验证或模拟异常flags。Conv、RawPrep、RMS/QKnorm其余add/mul用NumPy单独FP32运算，无合并FMA。exp使用原degree7 Horner，各节点FP32，系数由math.log计算后FP32，不使用np.exp；RawPrep softplus采用原odd-atanh15，不使用np.log。RawPrep冷chunk缩放使用math.sqrt(128)生成FP32常量，未改为decode除法。上述只为现有参考值路径候选，不称严格完整数值PASS。RMS源码96–110、147–160、248–278；C2源码82–89、365–396、435–461，均记录pin。
