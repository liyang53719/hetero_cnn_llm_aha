# Qwen2 Matrix 候选异常标志独立审计（TEMP）

## 实际新增
- `audit.py` 用整数 dyadic 表达精确 BF16×BF16＋FP32 和，独立 RNE 到 FP32；按原 `EmitHeteroBF16Fma.scala:89–95` 的 tininess_afterRounding 输出五位 flags。有限输入范围内 invalid/div0 为0；非有限与未BF16量化输入直接拒绝。无改变硬件或原fatal政策。
- 8个固定预期案例覆盖精确最小subnormal、tiny-inexact归零、舍入至min-normal后不报underflow、overflow、负零、抵消、halfway even；3个非法输入拒绝。普通及 `-O` 均通过，检查不依赖assert。
- 19,797组有限定向/确定性随机三元组，整数oracle与既有Fraction oracle的位值和flags逐项一致，且候选FP64再FP32路径位值一致。
- 哈希复核真实权重和上一轮M128中间数组。Q/K/V/O/gate/up/down各取token0/63/127、列0/中间/末列，共63个输出，每个走完整K。163,584个累加步骤逐步与候选位值比较，63个末值与保存数组一致。各步flags计数见RESULT，采样仅出现0与1，无2/3/4/5；不代表未采样无underflow。
- 使用原真实输入，仅内存读取，不生成/上传权重和数组，不重复完整21-op运行。

## double-round 风险边界
BF16乘数各8个有效位，因此精确乘积至多16有效位，FP64可精确表示所有有限BF16乘积（指数范围亦覆盖）；但加FP32累加器仍可能发生FP64舍入，不能仅凭乘积精确就宣布两次舍入等价。当前定向/随机及真实完整K采样未见不一致。没有完成全部有限三元组形式证明或全矩阵逐步验证，因此仍 `NOT_QUALIFIED`，不得替代HardFloat或把采样当全数值PASS。

## todo / ongoing / done
- done：独立整数oracle、边界测试、7阶段真实采样逐步值/flags审计。
- todo：全运行异常flags资格、与原Chisel/HardFloat实际输出/状态对照。
- 完整五块M128硬件仍0/5，未执行Chisel/RTL；原head4 underflow FAIL不变。无利用率实测。

复现：在原工作区依赖与payload恢复并hash核验后，`OPENBLAS_NUM_THREADS=1 timeout 180 python -O round_20261110T0933/reference_flags/run_audit.py`。脚本CPU120s/AS2GiB，输入样本确定，只有摘要输出。
