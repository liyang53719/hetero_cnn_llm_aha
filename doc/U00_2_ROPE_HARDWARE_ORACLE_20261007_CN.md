# U00.2：按实际算术建立独立 RoPE 硬件 oracle

最新结论：已有RTL与独立硬件oracle逐位一致；source-native模型精度已发现远端真实输入反例（0.0625 > 原0.03125），保持BLOCKED。见文末反例与独立验真记录。

## 本轮边界

本轮保持官方 native BF16 reference、原 RTL 算术、operator/block 门限不变。新增 oracle 只覆盖现有 `fp32_rope_pair` 和 `fp32_rope_pair_pipe` 的 FP32 输入输出算术。它不是完整 Qwen3.5 block golden，也不关闭 U00.2/U01 或整 block useful-wall MAC≥90%。

输入复用固定 Qwen3.5-0.8B revision、真实 embedding→层2→层3 的 cold/carried M128 链。取官方 BF16 Q/K Norm 与官方 BF16 cos/sin，逐位扩展为 FP32。因此这是明确的“相同组件输入”条件比较；不声称硬件独立生成了这些上游值。

- Q：8 heads ×128 tokens ×32 split-half pairs ×2 cases =65,536 pairs。
- K：2 heads ×128 tokens ×32 pairs ×2 cases =16,384 pairs。
- 实际输入总计81,920 pairs；另外2,055个算术样例检查非BF16 FP32、FMA区分、ties-to-even、signed zero、subnormal和异常位。
- 软件完成 i↔i+32 配对。256维中的非旋转192维、partial-RoPE搬运、位置与三轴MRoPE、cos/sin生成器和BF16 store均不在该 RTL gate 范围。

## 冻结已存在的 RoPE 算术

`integration/gemmini/EmitHeteroFP32Alu.scala`、`EmitHeteroFP32Pipelines.scala` 与 `rtl/sfu/fp32_rope_pair*.sv` 已逐字节固定。HardFloat分别执行四个 FP32 RNE 乘积和两个 FP32 RNE 加法，tininess-after-rounding；没有 FMA 融合：

1. ec=RN32(e×c)，os=RN32(o×s)，es=RN32(e×s)，oc=RN32(o×c)。
2. e′=RN32(ec−os)，o′=RN32(es+oc)。
3. RTL 输出仍为FP32。报告内的末端BF16仅为软件投影，不宣称实际BF16转换RTL已测试。

新 `src/heteronpu/rope_hardware_oracle.py` 用整数dyadic数精确计算每一步，再在该步舍入到FP32。它不是直接用理想FP64 pair替换原算术，也不依赖NumPy BLAS、Torch后端或FMA。有限subnormal和signed-zero受支持；NaN/Inf输入及中间overflow明确拒绝，避免以有限域测试宣称全IEEE特殊值覆盖。

官方 native 仍执行两个BF16产品舍入后再BF16相加。本地CPU产生的夹具上，软件终端投影与native有26,091个输出位不同，四个Q/K分组最大绝对误差均0.03125，均值均小于0.000881，恰好仍在既有operator门限内。这只解释RoPE组件差异；先前126项source-native诊断的本机9项/GitHub CPU5项失败、QK最大差1.0并未被修复或替换。

## 实际结果与独立复核

- 两个原RTL实现各执行83,975 pairs，所有输出位和5位异常标志完全一致；共335,900个FP32输出值。组合wrapper128,459 cycles /34,582 stalled-output cycles；pipeline wrapper1,091,686 cycles /251,916 stalled-output cycles。计数含本testbench的人工输入间隙和输出背压，不是吞吐或MAC利用率验收。
- 独立C fenv参考另外生成10,000个全指数范围raw-bit pairs，Python oracle与两个原RTL均0不匹配；包含4,306个underflow+inexact例和5,692个inexact-only例。
- 独立review发现min-normal×(1−2^-24)虽然编码结果是min-normal，HardFloat的precision-p/unbounded-exponent after-round tininess仍置underflow。仅修正新oracle的异常位解释，生产RTL未修改；独立RTL证实结果00800000、flags03。
- 最小独立Chisel workspace从固定HardFloat commit生成真实RTL；冷缓存重新下载339项Maven依赖并重新编译23个Scala源，生成文件SHA一致。该冷测的bootstrap归档复用已下载且已校验的固定原字节，Maven/sbt缓存为空；不宣称从全空网络环境重新获取bootstrap。没有用shortreal、DPI或软件float替代硬件。
- 生成器在每次门禁重新clean/compile/emit，校验完整workspace及HardFloat源码目录、依赖hash和manifest；输出数据与所有异常位同时检查，背压期间数据/valid/flags稳定，最后额外drain防多发。

- 最终保存夹具路径与同进程重新运行官方前缀/audit路径均通过；后者在Python `-O`下执行完整生成与RTL回放，输入/expected/实际输出逐位相同。新测试normal与`-O`各41通过，focused280通过；全仓2,042通过，原5个baseline失败保留，不重复修改无关失败。

## Matrix / Norm / Attention 实现核对

完整硬件oracle尚不能从泛化v0文字推定。当前存在不同实现路径，必须明确选型和数据边界。

### Matrix

现有 `rtl/integration/qwen2_matrix_command_endpoint.sv` 选择Revision8B-B固定16×32、5上下文、FIFO8。`EmitHeteroBF16Fma.scala` 与 `bf16_context_fma_pipeline_lane5_rev8b_b_candidate.sv` 执行BF16×BF16+FP32 fused RNE。

`chisel/continuous_prefill/.../StreamingDense.scala` 中每输出从+0开始，按递增K做单一FMA累加链；五上下文只是交错，不改变求和树。Dense写回原FP32。`MatrixPipeline.scala` 的8 slice分列构成16×256，不是split-K。FP32容器在入口舍入BF16，原生BF16权重保位。不能直接把官方“每个linear产物BF16”套到现有FP32写回上。

### Norm

- Continuous `Qwen2Block.scala:251-266`：FP32 square；按元素顺序串行相加；乘1/H；加epsilon；正确舍入sqrt，再除法求倒数；依次x×inverse×gamma；最后BF16。现有gamma是直接乘weight，未实现Qwen3.5的1+weight。
- `fp32_rmsnorm256_chunked.sv`：16路平衡树后串行相加16个chunk；一轮LUT/Newton rsqrt；两个FP32乘法；FP32输出。
- `fp32_norm16_rms_l2_pipe.sv`：16路平衡树、两轮LUT/Newton、FP32输出。`operator_sfu_norm_endpoint_v3.sv`只有16元素或4组×4元素，不能宣称H1024聚合已实现。
- H1536专用Norm另有可选中间BF16舍入；不能作为H1024/QK256等价替代。

### Attention

- Continuous QK：16条FMA链分别累加i,i+16,…，然后顺序相加16个accumulator并FP32缩放。
- Continuous softmax：顺序key扫描、degree-7 exp近似、顺序FP32求和与倒数；PV入口将概率/V各舍入一次BF16，递增key做FMA，输出FP32。
- 另一路 `attention_matrix_tile_sequencer.sv` 的QK为递增维度；PV先处理32个high-BF16概率项，再处理32个low residual项。不能把这个hi/lo路径套到Continuous概率单BF16路径。

## 下一真实实现门禁

1. 选择并记录当前0.8B所用实际Dense/Norm/Attention路径，明确每个producer的FP32/BF16写回策略；以实际RTL复验算术顺序。不能用NumPy/Torch的归约顺序代替。
2. 解除Continuous `hidden==heads×headDim` 假设：0.8B为H1024、Q宽2048、packed Q/gate4096。实现packed Q/gate分离、Q/K每头256维Norm的1+weight、sigmoid输出gate及独立head几何。
3. 将partial64-RoPE的split-half packing、官方表输入和BF16存储接口接入真实owner，验证非旋转192维和位置/缓存连续性。
4. 扩展独立硬件算术图；每个producer保留所有隐含节点，以实际整block生成RTL喂同一输入。原native源模型比较单独保留，任何差异不得通过放宽阈值隐藏。
5. 三模型完整block数值、GDN BF16链、35B实际路由/cache、固定资源整block useful-wall MAC≥90%继续OPEN。

`HeteroQwen35DenseAttentionPrimitiveV3` 当前是micro-op sequencer，列出了这些算子并不代表完整数值datapath已存在。

## 复跑与证据

`scripts/run_rope_hardware_oracle.py` 每次内部调用 `scripts/generate_rope_hardware_primitives.sh`，从固定HardFloat源码clean/compile/emit真实Chisel RTL，然后仿真；不能用已有SV/manifest跳过重新生成。保存每个输出与异常位、RTL源/生成文件/依赖SHA、编译命令、完整仿真日志和backpressure计数。默认保存输入只接受固定已核验audit报告SHA；fresh模式内部运行固定audit并校验返回/报告一致性，CLI没有“信任任意报告”的开关。

最终本机结果、测试和独立review见 `reports/execution/U00_2_ROPE_HARDWARE_ORACLE_20261007/`。绿色CI仅代表名称所列的现有RoPE pair组件门禁；不代表完整Qwen3.5语义或三模型/90%验收。


## 远端真实输入反例：RTL一致性通过，source fidelity拒绝

提交 `2cb5c6c439b38e361fc64ecdea70b18ee7156570` 的七项CI全部通过。实际RoPE产物已下载，83,975个expected由独立整数oracle重新计算，两个DUT的完整文本/NPY输出、异常位、source/manifest SHA均再次核验；远端生成RTL与本地逐字节一致。此结论只接受已有硬件算术的忠实重现。

GitHub CPU产生的真实carried输入同时给出新的model-accuracy反例，不能继承本地四组诊断均通过的结论：carried Q的token110、head4、channel50（绝对position238），同一BF16输入e=bf92、o=c110、c=3f80、s=3ce1。

- 当前硬件e×s为FP32 bd005200 = −0.03132820129394531，与o×c=−9相加得到c1108052，再投影BF16为c111 = −9.0625。
- 官方先将e×s舍入BF16为bd00 = −0.03125，相加正好落在c1108000 = −9.03125的BF16中点，ties-to-even输出c110 = −9。
- 绝对误差0.0625，超过原operator上限0.03125；carried Q中恰好1个输出超限。远端全部四组共26,348个位不同。
- 完整source-native BF16诊断仍为BLOCKED，5项比较失败、QK最大差1.0。绿色组件CI不能升级source fidelity、完整block或MAC90%。

反例原字节、远端完整component结果、七项exact-head CI记录及校验结论保存在 `reports/execution/U00_2_ROPE_SOURCE_FIDELITY_20261007/`；新增固定反例测试断言该精度门禁必须拒绝。未更改生产RTL、native实现、舍入合同或容差。

下一有界实验：在固定Q/K输入及cos/sin下，独立记录两个乘积和最终和，对比四个软件候选（均不替换生产硬件）：两个乘积都保持FP32、仅cos乘积BF16、仅sin乘积BF16、两个乘积都BF16。先要求最后一种与官方逐位一致，并定位每种候选的误差/中点分叉；再单独评审是否引入明确版本的硬件producer策略。不能以BF16末端输出或本地样例通过代替对所有真实输入和下游producer的验收。
