# U00.2：原SiLU逐节点数值与单上下文逐拍候选

范围：candidates/qwen2_resident_matrix/sfu_silu_cycle_candidate。
保留原文件及默认Chisel配置；这里只增加可独立检查的软件功能/边沿模型。

## 本轮计划与检查项

- [x] 锁定原VectorSilu/BlockScalarFloat、两种已有数值profile、HardFloat divider计数源码。
- [x] 使用既有精确有理数FP32/RNE参考，保留每一Mul/Add及原异常政策。
- [x] 默认原wrapper/options0/LegacyV0，显式关闭候选控制器及options16。
- [x] 建立只用16个原ALU和16个原divider的单上下文microsequence。
- [x] 保留六相位global allValid，无提前lane复用、无额外ALU、无免费payload FIFO。
- [x] phase4/5仅在既有Qwen2OfficialBf16V2 profile按原patch做BF16边界舍入。
- [x] divider options0逐拍25/26；可选options16逐拍14，明确新增递推逻辑与STA义务。
- [x] accepted债务、不可反压divider返回捕获、响应长背压、失败/abort排空与复用检查。
- [x] 有限BF16、signed zero、cutoff边界及逐节点/逐相位原recipe比较。
- [x] 独立审阅GO；审阅发现的held-response abort发布问题已修正并回归。
- [x] 14项候选测试及4项摘要冷测试在普通/-O各通过；相关52项测试+81个subtests在普通/-O通过。
- [x] 冻结96个事务证据：14,592个exp节点与9,120个phase-lane值比较通过。
- [ ] 新控制器真实RTL实现/协议/数值测试；options16真实数据通路等价检查。
- [ ] 新mux/feedback及options16逻辑的综合、面积、功耗、STA。
- [ ] 真实FFN bank仲裁/输入输出服务与完整block接入。
- [ ] 三模型典型block数值门与useful-wall MAC≥90%最终验收。

## 观察值的边界

完整向量gate=0时，输入edge0，原wrapper首次response在edge61；microsequence
options0在edge49，options16在edge38。gate=1时前两者为62/50；全cutoff为44/32/21。
这些是逐节点实际运行所得的候选模型边沿，未运行RTL或native重任务，也不代表
物理1ns/800MHz时序。完整exp的21个ALU服务边沿+1个转换边沿仍为单上下文串行。

原options0移除12个wrapper边沿并没有改变25/26拍divider递推，更没有证明完整
block可达80%或90%。options16保留16个实例但每实例多一组trial/subtract/select；
configuration_ledger.json已明确不同物理成本与timing configuration。当前bank
端口、FFN tile生命周期及Dense重叠均未计作已实现。

数值配置差别明确可追溯：默认LegacyV0保留FP32 phase4/5；既有Public profile
Qwen2OfficialBf16V2在phase4和5做BF16，phase5读取已舍入phase4。源helper的
非有限输入提前检查与Chisel逐相位检查不同，模型保留Chisel规则并披露边界。

独立审阅已GO；下一步选择一个明确配置进入RTL。不要将软件divider callback
共享同一结果误写成options16硬件等价证明，不要扩大已冻结数值门限。

## 最终证据与审阅

未发布的原始完整报告SHA-256：
b58b8de6ecfc301b9b18f6128ceea4ef9cdbeb5f109714443a23a974107c6ebc。
该690162-byte完整报告已在本地原样保留。发布的EVIDENCE.json改为安全紧凑摘要：
摘要60745 bytes，SHA-256为
731cf390c977da4cee36eae414058016bf1bd23f85f3a80f2e24d0f4770cb2b4。
只含配置、计数、原完整报告hash、每phase/全节点hash和调度边沿，不含任何
input/output/phase payload数组或其可逆编码。复现脚本按需在本地/CI重新生成
完整报告，但只允许显式保存至仓库外且不得覆盖已有文件。

摘要绑定候选模型、原source pins、配置ledger、测试和运行器hash；冷回归逐事务
从collect()派生摘要核对。原96个results的canonical hash仍为
553f294e20d95907e4de92e73627a51fde6d93f72bc49676ea71199497fc1843，
模型、算术及原14项测试语义没有变化。96个事务覆盖16个输入向量×6个命名配置组合；
其中12次原政策预期错误，非意外失败，不转写为“所有输入成功”。

原profile差异示例：gate=3f8d0000、up=3fa60000。两profile phase0..3相同；
phase4原FP32为3f53a7e7，Official舍入为3f540000；phase5 Legacy为3f893ee0，
Official先用已舍入phase4得到3f897800，再舍入为3f890000。每个中间值都保留
并比较，没有在最终输出再替换为理想FP64或原生参考。

审阅额外发现：held成功响应若收到abort不能继续发布。修正后响应payload保持
不变，另一路sticky cancellation保持到ACK，并禁止publish，包括abort+ACK同拍。
所有已接受divider请求仍先排空；后续新事务只能在ACK后下一拍接受。

本地verification/保存普通/-O及相关回归日志（不纳入本轮发布）；已提交review.json
保存独立审阅与复现结论。批量pytest使用--import-mode=importlib，
避免仓库多个test_model.py的默认模块名冲突；曾出现的collection失败另存日志，
没有修改既有测试。没有执行native、RTL或完整block重任务。

摘要发布差异独立审阅GO：4项冷测试普通/-O各通过，逐事务核对投影与无payload
规则。原模型/算术/14项测试/配置ledger/source pins均逐字节不变；review.json
保留原算术GO，另附本次摘要审阅，未重新解释原硬件能力边界。
