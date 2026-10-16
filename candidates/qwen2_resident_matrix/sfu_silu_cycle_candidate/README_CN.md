# 单上下文16-lane SiLU功能/逐拍候选

这是独立的小型Python候选，没有修改原Chisel、原数值入口或已冻结文件。
默认 Configuration() 仍为原 LegacyV0、legacy_wrapper、divider options0。
microsequence 和 options16 都须显式选择。具体配置/资源边界在
configuration_ledger.json；依赖源文件SHA-256在source_pins.json。

## 数值与控制

- 完整exp保持17个独立FP32/RNE节点，外加1个floor转换边沿。
  每拍每lane最多使用已有一个ALU输出，不允许FMA、不借用vector ALU。
- 完整SiLU继续按exp、1+exp、倒数、符号因子乘、gate乘、up乘的六相位执行。
  cutoff仍执行scale乘后选择零；exp内部flags仍忽略，外围原fatal policy保留。
- 两种命名数值profile均来自既有源码。LegacyV0全程FP32；
  Qwen2OfficialBf16V2来自既有chisel_policy.patch，只在phase4、phase5做BF16。
  对应Public软件入口是official_bf16_dense_silu_v1 / sf_vector_bf16_v1。
  phase5消费已舍入的phase4。不存在任意精度开关或放宽容差。
- 所有配置保持global allValid屏障。早结束的cutoff lane、25拍先返回lane
  都持有结果，等最慢lane完成本相位；没有提前复用lane或第二上下文。
- 除法只逐边沿执行已审计的原counter递推。商的数值由既有有理数FP32参考
  callback给出；这里没有执行divider商位数据通路，也没有证明options16 RTL等价。
- options0正常1/1、1/2仍为25拍，其余实际SiLU分母可以26拍；options16为14拍。
  options16新增第二组trial/subtract/select逻辑，明确是新资源/时序配置，
  不能宣称同面积、同关键路径或已达时钟目标。

精确callback从既有test_prefix_owners.py提取原exact/rn/ref_*函数，
不import其NumPy/native执行环境。原exp函数也按原AST独立执行做逐节点比较。
新增flags计算保留HardFloat after-rounding tininess细节，不能仅看最终exponent：
00800000×3f7fffff→00800000仍有UF+NX；
00800001×3f7ffffe→00800000只有NX。没有修改共享旧callback。

### 边沿口径

输入接受为edge0；本拍捕获的结果在下一拍可见；最后response ACK之前始终有
一个accepted debt。返回保持期间不接受新请求，ACK同拍也不接受新请求。
不含任何memory/bank馈送成本，以下均为模型观察值，不是RTL测量：

|输入|原wrapper/options0 首次response edge|microsequence/options0|microsequence/options16|
|---|---:|---:|---:|
|全lane gate=0，完整exp，divider25|61|49|38|
|全lane gate=1，完整exp，divider26|62|50|38|
|全lane gate=80，cutoff，divider25|44|32|21|

完整microsequence有21个ALU服务边沿、1个转换边沿、1个divider接受边沿，
再等25/26或14拍并执行上述3个已计入的后续Mul。首次response edge口径
比“22+25”的无握手必要界多2：divider接受边沿和最终结果可见边沿。
默认wrapper每个六相位还有issue/collect各1，共12个边沿。

## 存储、背压与异常

只用一组原input.gate/up、value、probability及每core原a/b/out/frac/
horner/product等工作寄存器的概念别名。返回pulse捕获在每core out，最后
packet保持在vector value。Python trace/phase_trace为只写观察记录，不参与调度。
无新payload FIFO、无双帧、无免费重叠。实际新mux、控制、tag接线及物理落地待做。

外部abort是本候选wrapper的额外协议：停止新节点，排空所有已经接受的divider
pulse，再保持terminal error直到ACK；abort不能改写已经对外可见的held packet；另一路sticky cancellation保持至ACK，
禁止发布，包括abort与ACK同拍。
这不是对原Chisel存在abort功能的声明。普通算术失败则照原相位屏障收齐后结束。
Public C++ helper会提前拒绝非有限gate/up；本模型遵从Chisel的逐相位输入检查，
因此非有限up在phase5才拒绝。有限输入profile对比有效，未声称两者异常时序相同。

## 运行

在仓库根目录，仅需Python标准库：

```sh
python -m unittest candidates.qwen2_resident_matrix.sfu_silu_cycle_candidate.test_model -v
python -O -m unittest candidates.qwen2_resident_matrix.sfu_silu_cycle_candidate.test_model -v
python -m candidates.qwen2_resident_matrix.sfu_silu_cycle_candidate.run_evidence
python -m unittest candidates.qwen2_resident_matrix.sfu_silu_cycle_candidate.test_summary -v
# 可选：完整逐阶段报告只生成到仓库外，且不覆盖已有文件
python -m candidates.qwen2_resident_matrix.sfu_silu_cycle_candidate.run_evidence --full-output /tmp/silu-full-local.json
```

亦可在既有pytest环境用--import-mode=importlib运行本目录和sfu_microsequence_audit。
发布的EVIDENCE.json只含96个事务的配置、输入hash、每相位hash、完整节点trace
hash、阶段计数、输入/响应/ACK边沿和预期异常；没有输入/输出/phase payload数组，
也不以base64等编码保存数组。counter_sets是按counter_names列出的普通计数器值，
phase_capture_edges是调度元数据，均不是浮点数据。完整报告只在collect()内存中
生成；需要调试时可显式输出至仓库外，禁止覆盖已有文件。

原始完整报告690162 bytes已在本地原样保留，其SHA-256为
b58b8de6ecfc301b9b18f6128ceea4ef9cdbeb5f109714443a23a974107c6ebc。
摘要同时保留该hash、原96个results的canonical hash和当前再生完整报告hash；
源码/说明变化会改变报告元数据，不能把当前完整报告说成原文件逐字节复本。
原96个results仍须完全相同，摘要冷测试逐事务核对所有计数和phase/node hash。

正常与-O测试含有限BF16、signed zero、cutoff两侧、
精确/非精确subnormal、异常policy、全局屏障、长背压和逐边沿abort/drain。

下一门是独立审阅后选定配置的真实RTL实现/数值/协议测试，再分别做STA和共享bank
仲裁接入。三模型完整block及useful-wall MAC≥90%仍未验收；不以这些孤立向量
边沿计数换算成完整block实测吞吐。
