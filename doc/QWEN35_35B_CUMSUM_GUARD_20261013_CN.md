# 35B 有界 FP32 累加策略（2026-10-13）

## 解决的具体差异

固定 Torch 2.10.0+cpu / DEFAULT / 单线程中，FP32 cumsum 的 CPU running 是 binary64，
每项输出转 FP32，但输出舍入不反馈到 running。这与 Q/K 的 FP32 8lane sum 策略不同。
当前实际 Prep g 上，旧逐项 FP32 cumsum 在 M16/M128 分别有768/2483个不同输出。
本批采用现有 Vector16 的 FP32 Add 构造显式有界候选，没有添加 FP64 算术单元。

上游出处固定为 PyTorch commit 449b1768410104d3ed79d3bcfe4ba1d65c7f22c0：
- aten/src/ATen/native/cpu/ReduceOpsKernel.cpp，SHA256 5ab4ebf7f6d06f4f036c2ae710d893c5f3ab74be5883fc524c71d95159e845b0。
- aten/src/ATen/AccumulateType.h，SHA256 f1defbdc257362abe5c4530baf558bb58880d8d5522b411da12b466cf6de7c08。
官方模型 chunk 函数、版本和参考实际 shape/stride 同时进入机器证据；不以 RMS 类来源冒充 cumsum 出处。

## 显式范围及证明

新策略 35b_guarded_two_sum_fp32_span18_64 只允许 GROUPED_35B 显式选择；旧默认仍逐项 FP32。
每 head/chunk 重新初始化 hi、lo、指数范围和计数，最多64项。输入只接受非正 normal FP32 或±0；
非零 unbiased exponent 最大120，运行期范围跨度最多18。subnormal 输入、NaN/Inf、正数、超界拒绝。
这些条件不是官方模型全域约束，而是这个候选明确收窄的支持域。

每项先 TwoSum(hi,g)，再 TwoSum(lo,error)。第二次的 discarded residual 非零即 Numerical，
不发该项输出 Add、不丢弃误差继续算、不夹断。成功时以一次 Add(high,low)产生输出，不反馈输出。
两次 TwoSum 各6次 Add，输出1次，共13次原 Vector Add。异常后实例 poisoned，只能新 chunk 实例恢复。

令最小非零指数为 emin，则各输入在 2^(emin-23) 的整数网格上；最多64个同号项使绝对整数和
严格小于 2^(30+emax-emin)，span≤18 因而最多48位。固定 CPU binary64 能精确表示所有前缀。
第一次 TwoSum 精确分解 hi+g；第二次残差必须为零，才证明新的 high+low 等于精确前缀。
最终一次 FP32 Add 与官方精确 running 转 FP32 一致。emax≤120 保守保留64项累加的溢出余量。
实际 Vector 的 RNE、FTZ/DAZ、exception flags 检查仍有效；不能仅凭输入 normal 承诺所有步骤均接受。
最低 normal 附近的精确 subnormal residual 已覆盖，非法运算/异常仍 fail-closed。

已保存一个纯合成64词反例：指数跨度16，朴素 TwoSum 加 rounded-low 在第63项给 c2bd3822，
官方给 c2bd3823。新策略在该项检测 discarded=ac000000 后拒绝，共831次 Add，不能发第832次。
因此本策略不是无条件支持全部 span18 输入，更不是通用官方 cumsum 替代。

## 本批实际证据与边界

1. 同输入组件重放：读取前批已冻结实际 Prep 输出，检查其 summary、原源码和 native 哈希，
   按官方实际 M16/M128 shape/stride 调用 Torch cumsum。新模块对96个 head/chunk、6144个输出全部逐bit一致。
   M16为16个真实 token 加每head48个padding，共2048项，26624次 Add；M128为128个真实token，4096项，53248次 Add。
   每项真实执行运行期检查，未继承早先 span23 probe 的结论。
   该重放没有重新运行 producer，也没有执行完整 chunk 矩阵运算。
2. 同一实际 ChunkOwner 的32头 M2/dk16/dv32 合成完整小例：abort、drain、reset后继续，全部32个
   chunk64完成；2048项、26624次 Add。Q/K/V为零，输出及65536B缩维state全0；head0两项g产生非零hi/lo，后续head的scratch gates全部为零，核对carry未泄漏。
   scratch/output/state均未发布。生产 dk128/dv128 和真实35B完整chunk没有由此通过。
3. 真实 owner 的后期反例：head0、row63 Numerical；此前63项 scratch 已写ACK但仍私有，
   831次 Add、无成功终态或状态提交，Scalar/Vector释放且pending排空。policy错配、运行期替换拒绝。
4. ±0、normal最小值、subnormal residual、span18/19、emax120/121、64/65项、NaN/Inf、正数、
   错舍入模式和 poison 后重用均有测试。测试参考首版误用了 NumPy cumsum 的首项负零赋值；
   按已核实官方 +0 running 初始化改独立参考后重测，不修改候选算术、不继承失败通过结论。

## 资源与性能代价

同一个 Vector16，逐项只用一lane Add；不新增 Matrix、Scalar、FP64单元或tensor缓存。
hi/lo为两个持久32bit补偿状态，加指数/计数/control元数据；原cumulative输出和数据包寄存器不含在这两个word内。
TwoSum算术的临时槽估计需要结合生命周期复用审查，不能把hi/lo计数当作完整寄存器总数；
尚未绑定生产 Chisel，也没有综合证明完整 live-register 上界。原 chunk generator 的其它局部list缺口仍在。
输入、scratch、state外部DDR布局及读写路径不因这项策略增加，但串行 Add 请求由1次变13次。
软件 transport ticks不包含每次真实 Add 延迟，不能用其不变声称无吞吐代价或流水达到目标。
本算子执行 MAC为0，Add请求实计；完整chunk有用MAC、硬件完整周期、占空比和利用率仍未知。

## 剩余依赖

原 exp_negative 的≥80归零仍未在 chunk 中改为新渐进下溢策略。实际35B完整维度还需要
同一次真实producer的memory/Scalar/Vector与staging交接、后继数值门、warm state及最终joint fence。
Prep g最大4ULP仍只诊断；same-input standalone chunk没有新批准阈值，本批没有擅设阈值。
原完整链BF16/state/final门不放宽，模型组件证据不能替代完整block或RTL通过。

首轮聚合冷门发现原实现身份测试只复制三个旧实现文件，遗漏新cumsum依赖。已将新模块纳入
IMPLEMENTATION_SOURCES及逐文件变异检测，独立身份测试通过；算术未改，重新冻结并重跑组件及全部冷门。

最终冷门543项、51套、155源，零skip且源码前后不变；完整计划/几何/控制列表338项通过，
最终计划清单91项重测通过。机器摘要绑定最终5项owner/边界日志与重冻结的同输入组件原raw记录。
