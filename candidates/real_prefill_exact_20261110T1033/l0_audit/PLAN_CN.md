# L0 underflow 精确依赖锥审计（TEMP）

不是仅对失败乘法重算：从已哈希冻结的真实Conv/AB边界与A_log/dt_bias开始，独立Fraction重新执行每个FP32加/乘/除、精确sqrt邻点RNE、Softplus Horner、decay和所有相关前缀和/ExpNegative。head0进一步对Q52与K28的完整128项归一化、Q缩放、128项独立乘再加dot及pair exp逐节点计算；heads3/11/13对完整128项K归一化、beta、KB和累计decay exp计算。所有必需prepared字与已保存候选逐字一致，10711节点复现四个tiny-inexact末操作。输入边界及162源码闭包相关文件SHA重新核验。

结果：head0 row52/col28 phase6，b90b2091×05d1243c→801c6a52；另三head细节在RESULT。每个最终结果严格tiny_after且inexact，原fatal政策下应拒绝。没有规避underflow，没有填零或继续后半FFN。这里是独立参考依赖顺序，不是硬件首失败周期；旧head4硬件FAIL保持独立身份。

源码审计：GdnRuntimeRawPrepProtocolV7:34将16head映射Legacy归约/gate策略0（32head另有策略，不能将本审计迁移35B）；RawPrepOwnerV7:14–21、146–157是逐元素平方求和、epsilon、sqrt、reciprocal和Query FP32缩放及Softplus/exp。BlockScalarFloatPolicyV2:61–62、109–137明确degree7系数和Legacy range reduction，100-digit Decimal独立算ln2生成8系数/LOG2E，与冻结字一致。ChunkExecuteOwnerV8:20及40–46是升K、独立Mul/Add及phase6；DerivedAndPairV2Owner:163–164是KB、KBG和exp参数。精确Fraction源与这些Scala源均在PINS。

边界：没有重新资格化上游RMS/Dense/Conv全部输出；它们仍候选，本结果严格为从冻结Conv/AB边界至4个失败节点的精确复现，不是完整原Chisel或硬件数值FAIL/PASS，也不能证明无更早的其他失败。脚本round_fraction对精确零canonical +0，当前审计节点比较一致，不声明全域signed-zero资格。未运行RTL，五块完整硬件仍0/5。

实际执行普通及-O均exit0；CPU590s/AS2GiB/wall600s上限，实际不足1秒，无昂贵重复作业。无需依赖torch或C++算术oracle。数据只读取不上传；所有断言用显式异常，不受-O消除。
