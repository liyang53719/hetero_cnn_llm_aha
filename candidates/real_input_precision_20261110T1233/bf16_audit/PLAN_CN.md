# L3 M128 BF16 转换源码契约审计

## 范围及层级
Python 独立整数参考 vs 原 Chisel 源码的逐位翻译，以及已保存真实权重 M128 数学链的转换边界重放。没有执行 Chisel/Host/RTL；硬件完整 block 通过数不变。没有修改精度、数组、算术顺序或硬件。不继承给 L0。

整数参考用有效数的整数除法、余数与半途比较实现 RNE，不依赖浮点加偏置。保留符号零，非精确且舍入后指数为零才置 UF；有限溢出置 OF|NX=5。测试覆盖所有 65536 个 BF16 上半字各7种低半字边界及明确特殊数。

## 源码契约并不统一
- Protocol.scala TensorMath.bf16Rne 只输出值，无 conversion flags，NaN保留符号并静默规范化；不能将这里计算的NX/UF当作硬件上报。
- PartialRope64Owner.scala PartialRope64Math：NX=1、UF|NX=3、OF|NX=5、sNaN NV=16，NaN统一为正7fc0。Owner合并 scalarFlags，combinedFlags(4,1)任一位触发 Numerical；NX允许。
- QkNorm256Owner.scala weighted 路径：有限输入显式相同转换flags，合并标志，转换 UF 或 OF 直接拒绝。非有限输入由外层路径拒绝。
- GdnRmsNormFixedBankOwner.scala：标量与vector epilogue用无旗标TensorMath，转换后只另查BF16溢出；不能声称具有同QKNorm的转换UF上报。
- Bf16CausalGqaOwner/GdnElementwiseOwner等使用TensorMath，转换输出值和算术flags应区分。
- BF16输入在Owner内以Cat(word,0.U(16.W))精确扩宽；不是算术舍入。此处验证已存在BF16输入扩宽，不覆盖最初由原全精度checkpoint量化成BF16的过程。

## 实际链覆盖
重放上一轮已审七Dense、QK/PV、mask、softmax、gating、FFN、residual；截获每次物化，逐点整数参考与源码模型及旧参考值比较，同时逐stage对照原保存哈希。另完整partial64 RoPE的六个物化边界。四norm只重建原已审算术值并审最后BF16转换，不重复声称norm exact节点新通过。所有输入仍按旧manifest哈希校验。

## 失败归因与限制
原session56842完成值检查后写摘要遇NumPy int64 JSON序列化TypeError，不是数值不一致。保留失败日志；将计数显式int后原任务修复重测，最终身份见RUN_IDENTITY.json。
本审计是源码契约/独立数学证据，不证明硬件真实调度/flags正确接线、无死锁或完整RTL数值通过，无利用率数据。原head4 underflow FAIL不变。

## 终态
最终 session43861 exit0，32.949s。55个转换批次、5,160,960个FP32→BF16值全匹配，所有转换flags只0/1，无UF/OF/NV。四norm转换589,824值；RoPE245,760值；其余链4,325,376值。输入扩宽18,491,904词、非有限0。正常与-O边界小测通过。
