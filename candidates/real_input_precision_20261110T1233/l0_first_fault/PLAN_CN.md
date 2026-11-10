# L0 首错固定标量回归（参考资格，不是硬件首错）

新增可脱离权重/NumPy/torch运行的 Fraction FP32 RNE 最小回归。普通及 `python -O test_first_fault.py` 均 PASS。仅保留四组必要失败归因操作数/结果和一个 Conv tap 政策对照，无数据数组、权重或输入展开。未跑 Host、Chisel 或 RTL，未改算法/契约，未绕失败接 FFN。

## 原调用链与精确范围

实际 profile1 M128 的输入是既存 caller dyadic hidden、权重为真实 checkpoint。11:33 的既有上游独立审计已验证 input RMS → QKV/Z/AB ordered-K Dense → Conv4+SiLU 完整输出；本轮不重复大作业。10:33 已有 10,711 节点独立依赖锥从冻结 Conv/AB 到四个失败操作，本轮只重放最小固定末操作，不宣称重新执行全锥。

原始恢复源码身份见 PINS.json，不能将其资格迁移到另一个硬件哈希。

1. `GdnRuntimeRawPrepProtocolV7.scala:30–35` 对16 value-head选择 reductionPolicy=0/gatePolicy=0。`GdnRuntimeRawPrepOwnerV7.scala:15–20,145–158`：Conv 的 Q/K 做逐元素平方、升序 FP32 sum、epsilon、sqrt、倒数、归一化，Q再按1/sqrt128缩放；AB/a_log/dt_bias生成 beta 和 log-decay。该 Owner 的默认乘法显式为 **ScalarOp.MulIeeeRne**，不是默认 ScalarOp.Mul。Softplus和Exp内部各步仍按原策略，不能把默认opcode扩成整个公式无条件允许下溢。
2. Chunk load/prep 将 prepared 的逐token log-decay升序累计为G。原64token chunk顺序保持，不是128次M1替代chunk。
3. heads3/11/13：`GdnRuntimeChunkDerivedAndPairV2Owner.scala:163–169,181–190`，K和beta先做KB，随后mulKbg用payload(2)=KB乘 expG=ExpNegative(G[row])。失败分别是chunk0 (row16,col25)、(29,4)、(43,61)的KB×expG。
4. head0：`GdnRuntimeChunkExecuteOwnerV8.scala:20,40–46,94–114` phase6先升K独立Mul/Add形成 Q[row]·K[col]，`factorMultiply` 再乘pair decay ExpNegative(G[row]−G[col])。失败在chunk0 row52,col28最终factor乘。

**关键纠正：四个末操作走共享 Vector 请求，不是 ScalarOp.Mul 调用。** Derived和Execute均发送 payload.multiply=true、LegacyRaw；strict context 的 vectorPolicy=LegacyFatalUnderflow(0)令gradual=false。`UnifiedVectorElement32BankV4.scala:40–57`调用lane ALU并在legacy路径检查flags(4,1)，因此UF置位应返回错误。不能以 Conv/RawPrep 的 MulIeeeRne 放宽这里。

Conv区别：`GdnRuntimeConv4OwnerRecoveredV7.scala:123–132` tap乘选择MulIeeeRne，后续sign/activate默认Mul。`BlockScalarFloatPolicyV2.scala:90–100`两者结果RNE相同，只有前者接受UF/NX；invalid/DZ/OF仍fatal。此前7,084个tap tiny-inexact已有单独精确验证，本轮只用一个已记录标量检验政策区别。

## 固定末操作

- head0：b90b2091 × 05d1243c → 801c6a52，flags=3。
- head3：b7d2e6e8 × 062d4b57 → 8008ec42，flags=3。
- head11：393a1733 × 06a6baac → 007932bd，flags=3。
- head13：b986bf1d × 05fa37c6 → 8041d9ff，flags=3。

flags顺序NV,DZ,OF,UF,NX，3=UF|NX；tininess-after-rounding。精确subnormal无UF的控制例也验证，避免把所有subnormal错判fatal。严重flags在gradual政策仍拒绝。

这些是先前独立候选逐head执行报告的首错坐标，不是已证明的原Chisel全局首错周期。最小回归不能证明各head之前所有操作无更早旗标错误；旧head4硬件FAIL保持独立身份，不能将本轮数学复现称为新增硬件FAIL。完整L0与五块完整硬件仍INCOMPLETE/0 of 5；本轮无利用率结果。

## 临时文件

本目录仅源码、pin、摘要和测试日志；Python缓存不打包。没有删除已有数据或唯一证据，没有push。后续需在同硬件原Host做真实完整执行并对齐返回错误，仍不得更改严格政策来获得通过。
