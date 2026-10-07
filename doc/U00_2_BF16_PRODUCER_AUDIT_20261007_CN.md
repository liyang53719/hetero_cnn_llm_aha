# U00.2：0.8B 层3 BF16逐producer审计仍被拒绝

## 结果与范围

本轮恢复中断前的源码和完整数组，复用已固定的真实层3权重、真实官方embedding→GDN0/1/2输出及人工token-ID夹具。B1、cold M128与carried M128不变。独立NumPy参考从相同层3输入起步，后续中间量和carried KV均由自身计算；没有注入官方中间结果压低误差。GDN原始F32 A_log/norm及FP32 SSM保持原状，未新增GDN BF16双参考验收。

本机每个case保留57个数值producer，另比较output/K/V、RoPE cos/sin与mask，共126项。9项未通过原门限，状态为 `BLOCKED_BF16_PRODUCER_GATE`。最终output最大绝对差虽仅0.00390625，但不能覆盖隐藏节点失败：cold与carried的QK原始乘积最大差均1.0，scaled QK最大差0.0625；carried还有Q平方及post-attention norm边界超限。

门限仍是单算子max_abs≤0.03125、mean_abs≤0.005，整block≤0.05/0.01，未更改 `spec/numerical_contract.md`。新增FP32 softmax逐行概率和的绝对误差≤2e-5及masked位置严格为零检查，作用于BF16概率cast之前。完整数组保留，包括失败节点；不能只保存或报告最终输出。

## 首个差异与原因边界

- 两个case的首个逐bit差异都在input RMSNorm的FP32 mean，最大9.313225746e-10。NumPy与Torch CPU使用不同reduction后端，不能假定同一求和树。
- cold的input norm BF16结果仍逐bit相同，随后q_proj出现差异。因此首个BF16分叉可定位为相同BF16输入/权重下的GEMM输出舍入。报告给出选中dot的精确二进制有理数和两输出中点距离，不声称拿到了不透明的native accumulator。最大差坐标[0,111,3443]属于打包q_proj的gate半部，该具体旁证不单独解释QK失败；同一producer的Q半部也存在差异。
- carried的input norm在[0,22,942]首先出现一个BF16分叉：native -1.9453125、NumPy -1.9375。报告保留两者cast前FP32值及BF16中点距离，逐一核对各自RNE正确性。后续传播会放大隐藏节点差异，不能因此删除节点或放宽门限。
- 18个native GEMM另做“相同native操作数”的条件FP32累加误差上界审计，未发现上界违反。这仅帮助排查局部计算，绝不作为独立整图PASS；该旁路没有回灌NumPy参考，也未证明特定CPU实现或超越条件假设的形式化误差界。

## 官方eager语义与硬件v0的差别

官方eager的RoPE表达式会把两个BF16乘积各自舍入，再执行BF16加法；本轮source-native参考忠实记录这三处边界。既有硬件v0则规定FP32完成pair rotation后才舍入BF16。两者不能默认为同一数值语义。

因此即使未来source-native各节点通过，也只能叫该软件诊断通过。`hardware_v0_semantics_accepted`始终为false。后续必须明确source-native与硬件producer映射、冻结实际累加树/舍入边界，并按未变门限重验；本轮不改变任何硬件规范。

## 来源准入与失败关闭

- 保存夹具路径只接受独立冻结的原官方prefix报告SHA256；该报告再绑定完整NPZ及逐数组摘要。任意更改model、fixture、来源、比较结果或数组后重写自声明hash不能绕过此入口。
- 新运行路径先核对原prefix runner及其关键传递依赖的固定源码hash，随后在同进程执行原prefix runner，要求新目录和成功返回，内部取得刚生成报告的摘要。没有允许调用者自行指定可信摘要的CLI参数。
- 固定checkpoint/framework/config、运行时版本、source dtype、57处顺序和FP32解码容器、finite/normal边界均检查。既有output目录不覆盖，缺失或不支持的边界拒绝，audit运行期间源码变化也拒绝。
- local GEMM旁诊断修复BF16 subnormal半bin下界，保留zero分支；bit_different现在真正比较FP32位表示，包括正负零。这些是审计工具的准确性修复，不是为当前失败调整数值阈值。

## 复现与CI口径

已保存夹具复用：

```sh
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 HF_HUB_OFFLINE=1 python scripts/run_qwen35_bf16_audit.py --payload work/qwen35_layer3_payload --upstream work/qwen35_prefix_chain --output work/bf16_new --require-pass
# 本机预期退出2，并保留result.json和完整all_bf16_producers.npz。
```

在新机器上用既有collect脚本取得layer0、layer3、prefix的有界真实payload，再运行：

```sh
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 HF_HUB_OFFLINE=1 python scripts/run_qwen35_bf16_audit.py --payload work/layer3 --upstream work/chain --output work/bf16 --rebuild-layer0 work/layer0 --rebuild-extra work/prefix --require-pass
python -m pytest -q tests/test_qwen35_bf16_reference.py
python -O -m pytest -q tests/test_qwen35_bf16_reference.py
```

新增CI明确命名为source-native BF16 diagnostic not acceptance。它检查测试及完整证据收集成功，保留数值门禁退出0或2及状态，退出3/崩溃则失败；绿灯不代表数值门禁通过。CI摘要展示failed producer数量，完整prefix/BF16数组作为artifact保留30天。各CPU实际失败数以该次报告为准，不把本机9项写成跨后端硬编码期望。

U00.2保持ongoing，U01保持to do；三模型真实典型block、GDN BF16、35B route/cache、物理资源/流量和实际RTL全量数值及整block useful-wall MAC≥90%均未关闭。本轮没有执行RTL或测得利用率。
