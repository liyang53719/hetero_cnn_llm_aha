# U00.2：独立 all-products-BF16 RoPE RTL 候选

本轮新增明确带 candidate 名字的独立组件，不切换任何生产模块或默认精度策略。上一轮软件消融得到的“四产品 BF16 再相加、末端 BF16”现在落实为实际可综合 RTL 并使用真实生成的 HardFloat 进行仿真。是否接入完整 Qwen3.5 owner 仍是后续独立门禁，不能据本轮组件通过替换生产策略。

## 接口与逐节点合同

固定合同在 `config/upstream/qwen3_5_0p8b/rope_bf16_candidate_contract.json`。

- 输入为四个任意 binary32 原位 e/o/c/s，ready/valid 接受一组 pair。
- ec=e×c、os=o×s、es=e×s、oc=o×c，各自真实 HardFloat FP32 RNE；四个产品分别经实际 BF16 转换，再补低16位零送回 FP32 加法输入。
- even=FP32_RNE(ec + signbit_invert(os))、odd=FP32_RNE(es+oc)，无 FMA；两项各经实际 BF16 RNE。输出端口确实为16位，报告中只为逐位核对将其左移16位保存。
- 产品与加法仍使用原固定 HardFloat 发射器、RNE 及其 precision-p/unbounded-exponent after-round tininess。新 BF16 转换合同独立定义为“最终 BF16 编码 exponent=0 且 inexact 才置 underflow”，在最小 normal 边界不混用两种判定。
- 转换保留 signed zero/infinity；所有 NaN 规范化为正 quiet NaN 7fc0，仅 sNaN 转换置 invalid。有限值舍入溢出得到带符号 infinity，置 overflow+inexact。divide-by-zero 恒0。其余非零舍弃位置 inexact。
- aggregate flags 为4次乘法、4次产品转换、2次加法、2次末端转换的12个异常位字段 OR。实验 trace 保留每项原值和异常位；不能只比较 OR 后的位而遗漏中间错误。
- 输出阻塞时 valid、结果、trace、flags 全部稳定；reset 清空在途与已阻塞输出及计数器。wrapper 低有效异步 reset，内部 HardFloat 同步 reset 要求 reset 持续跨至少两次上升沿。
- 非有限值、FP32/BF16 overflow 都在实验接口上明确定义并实测；官方 native 逐位等价声明仅适用于两套冻结有限 BF16 源输入，不外推其 NaN payload/overflow 或完整模型语义。

## 验真分层

1. 独立 BF16 converter：穷举所有65,536个高16位，对每项取低16位0、7fff、8000、8001、ffff，外加固定随机位；覆盖正负、中点、进位、subnormal、normal、无穷及各类 NaN。
2. 每个 RoPE 节点：25列 trace 保留4个 FP32 产品/flags、4个 BF16 产品/flags、2个 FP32 和/flags、2个 BF16 输出/flags和总 flags。全部对新整数 dyadic oracle 与独立 C fenv 逐项核验。
3. 历史 native：直接读既有 hash 固定的 local/remote 紧凑 NPZ，不重新运行模型生成 expected。每个实现各检查163,840 pairs、655,360 products和327,680 outputs；产品边界和末端边界分开检查。
4. 协议：两个实现分别执行有输入间隙/输出背压的完整数据集，以及始终供数/始终 ready 的512-pair专门周期测量。执行在途 reset、满缓冲阻塞输出 reset、清空后的重放、64拍 drain防多发；每次核对 accepted/completed 计数。
5. 真实原语：每次完整 runner 都重新 clean/compile/emit 固定 Chisel/HardFloat，校验源码、依赖、生成 manifest 和文件 SHA；不使用 shortreal、DPI 或软件浮点替代 DUT。

C 参考使用 volatile binary32、FE_TONEAREST、禁 FMA/fast-math，并拒绝FTZ/DAZ宿主。若宿主 fenv 与 HardFloat 在编码min-normal处的FP32 underflow解释不同，只准许该节点数值相同、两者均 inexact、恰好UF一个bit不同的狭窄例外，完整列出后重算OR。BF16转换 flags 不允许此例外。

## 结构、吞吐与物理边界

每pair仍是4次FP32乘法与2次FP32加法，新增4次产品转换与2次末端转换。当前未共享的wrapper有6个converter实例。这是源码操作/实例数，不是综合 cell 数。组合wrapper使用6个带常量op的HeteroFP32Alu实例；生成的通用ALU本身包含加/乘路径，是否剪枝及实际单元数量取决于综合，不把源码4mul+2add当成最终资源证据。pipeline wrapper显式实例化4个MulPipe和2个AddPipe。

转换插在现有capture前，无额外架构级stage；这不证明满足原频率。trace输出和寄存器属于实验可观测性开销。没有综合、布局布线、STA或功耗测量，因此不声明面积降低、不降频、功耗改善或生产吞吐不变。仅报告专门无阻塞仿真的握手周期与II，时钟10ns只是testbench设置。

16位结果端口和converter通过不等于BF16 memory store。packing、byte mask、512位buffer、owner、DMA、partial64布局、非旋转192维、cos/sin位置/cache都未接入。没有带宽收益或MAC90%推论。

## 执行与后续

`python scripts/run_rope_bf16_candidate.py --output <fresh-dir>` 为实际候选RTL门禁；新CI名称明确 experimental-all-products-BF16，原生产FP32与其source-fidelity拒绝反例保持独立且原门限不变。

下一有界工作是评审producer策略及真实owner接口：Q/K256 Norm的1+weight、packed Q/gate4096→2048分离、partial64搬运、BF16存储合同及上游/下游producer联合数值，随后实际完整block。三模型完整数值和固定资源整block useful-wall MAC≥90%继续OPEN，U00.2 ongoing、U01 to do。

## 本轮实测结果

- 两实现分别回放177,458 pairs，其中163,840为两套冻结真实Q/K，13,618为全指数、signed-zero、subnormal、overflow、Inf/qNaN/sNaN的独立算术样例。所有25列数值及flags逐位一致；每个DUT的655,360个native products与327,680个native outputs均零差异。
- 独立converter实际RTL通过331,776组；另外独立review用exact-dyadic最近邻搜索核对1,703,936组舍入边界，避免重复使用主oracle的bias-add公式。
- 512-pair始终供数/输出ready专项：组合elastic wrapper首笔握手延迟2拍，接受/完成间隔均1拍；registered wrapper首笔9拍、间隔均10拍。首输入至末输出握手含端点分别514/5120拍；之后64拍drain单列。
- 全数据背压测试：组合wrapper271,478 cycles、73,075 output stalls；registered wrapper2,307,010 cycles、532,365 output stalls。总cycles包含测试启动与64拍drain，且有人工间隙/背压，不当作最大吞吐。
- 独立协议review另对组合wrapper四种occupancy状态执行19次reset，对registered wrapper全部六种FSM状态执行18次reset；每种实现1,024个有序事务、全部trace阻塞稳定、reset无残留和无多发。
- 本机独立C未使用任何min-normal UF差异豁免。特殊值支持只属于新实验合同；原有限域oracle及其明确拒绝行为没有扩大或更改。

最终源码hash、命令、完整仿真日志摘要、单位/全仓回归与独立review保存在 `reports/execution/U00_2_ROPE_BF16_CANDIDATE_20261007/`；全量输入、每节点oracle/C/RTL数组和文本由对应CI artifact保存。生成RTL、所有源及冻结数据均另带SHA，不能只按PASS字符串判断。

最终普通与Python -O候选/旧策略组合各316项通过；全仓2,317项通过，保留相同5个既有失败（exp2边界、terminal target inventory、arch schema、v69 control兼容、SRAM budget）。独立review发现新C参考可选文件CLI同文件别名会误截断输入，已按inode/device在打开输出前拒绝并新增6项保留原输入回归；随后全套生成/RTL/参考门禁重新执行并绑定最终C源hash。最初未设置PYTHONPATH的测试收集错误单独保留，纠正环境后的回归结果如上。
