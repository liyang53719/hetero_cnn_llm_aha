# TEMP：LegacyV0 独立 Python 全21-op参考

本轮补全原缺失的 RMS / QK / causal Softmax / PV / SiLU。所有运行期浮点算术均用独立Python Fraction及精确二进制RNE，numpy仅承载uint32数组；不调用C++、libm fma、Torch或BLAS。sqrt通过FP32相邻根二分和有理数中点平方比较准确舍入；div直接有理数单次RNE。

## 原顺序审计
- RMS：Qwen2Block.scala 554–573。每项FP32平方后按列递增独立加法；sum乘FP32(1/H)，加FP32(1e-6)，sqrt、1/sqrt，先x*scale再乘gamma；**最终总是F32.bf写回**，Legacy也如此。
- Dense：StreamingDense.scala 130–148单context逐K；FP32存储输入先BF16RNE，BF16乘积+FP32 accumulator单次舍入；不把存储改BF16。
- RoPE：Qwen2Block.scala 694–705半拆分，四次乘法、两次加法独立舍入。外部cos/sin表必须另验，未实现表生成器。
- QK：Qwen2Block.scala 709–814，16lane分组，每lane按depth+=16 FMA；lane0..15从+0顺序加，再乘headDim常数。HD128常数0x3db504f3；HD16仅小测试常数，不是缩硬件。
- Softmax：832–840，因果key0..token，max后差值、原exp(-abs)多项式、顺序sum、reciprocal，再乘exp。PV同样按key顺序BF16 ingress FMA。
- Exp：BlockFloat.scala 47–51、90–99，FP32 log2e，截断整数k，独立差值，degree7 Horner逐乘/逐加，乘2^-k；|x|>=80直接零。不是调用数学exp。
- SiLU：ScheduledSiluOwner非overlap使用VectorSiluOwner；六阶段exp/1+exp/reciprocal/sign factor/gate product/up product。Legacy无official的phase4/5 BF16物化。
- Scalar normal/div/sqrt保留tiny-after-rounding且inexact即fatal；不迁移渐进下溢候选的授权。数学Matrix FMA和vector路径尚未完整建模所有硬件exception/status、DMA/credit调度及非finite事件，故本参考仍TEMP，不是RTL资格。

## 验证及边界
19项正常/-O单测：精确RNE、signedzero、非finite拒绝、预算、逐K顺序、sqrt有界独立stdlib交叉核验、underflow拒绝、因果均值、完整21-op零权重残差恒等、非零烟测。另输出两组全21阶段SHA：M2/H16/HD16和M1/H256/heads2/kvheads1/HD128，FFN16。它们只是Python数学小规模自测，**不是固定4096硬件缩规模替代验证**。不声称完整M128数值/Chisel/RTL PASS；五块仍0/5。

完整真实M128约60亿MAC尚未执行。默认10万scalar操作预算；各Dense预检预算，不自动长跑。复用前轮round_fraction，SOURCE_PINS记录已验original162真实源码。下一步在此精确基线上审完整异常/常量表身份，验证可扩展加速实现的逐步等价，再接真实完整输入。没有push或SV生成。
