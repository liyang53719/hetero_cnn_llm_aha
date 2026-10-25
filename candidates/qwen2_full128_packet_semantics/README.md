# 完整 M128 原归档 accepted packet 内容与索引核验

**PASS_ACCEPTED_MATRIX_OPERAND_CONTENT_AND_INDEX_SEMANTICS**，仅一次离线原归档核验，**不是 DUT/native/reference/RTL 重跑**。原模型完整 M128 已发布的观测域与完整协议 PASS 保持；本包只新增accepted operands的内容/索引证据，不提升full29、非干扰或硬件资格。

## 本次真实范围

同一封存237,446,391-byte流（2,478,339帧）经一个新独立stdlib checker单次读取，确认19,200 groups及847,872 accepted operands：55,296 QK packets、792,576 PV packets。期待内容取自5个不变实际归档（q、KV parent、probability、presence、frequency），不是官方reference；独立整数cursor实现token/head/GQA6/causal/tail映射，逐544-byte `<272H` A16+B256 little-endian期望包只做SHA比较，不公开这些包，不执行FMA或改变舍入。

prob每个有效因果cell对应8个不同column accepted packets，不等于8次DDR probability读取。future presence/frequency0且固定sentinel保持；QK tail与PV未用lane显式期待0，不读取future K或补missing值。完整footer/EOF、控制字段strict types、group/result/done/reply/ticket/epoch和release均受检查；不把合法prefix当完整PASS。

根执行EXIT0、无outer timeout：inner31.205254672CPU/31.212121172982734wall，reaped31.24908CPU/outer31.260075226949994wall，reaped process peak RSS41,680,896B。原封定180CPU/240wall、单CPU、512MiB AS/256MiB sampled RSS、64KiB report限额不变；不是运行预算必能成功的保证，AS不等于RSS或aggregate-tree峰值。

独立actual审查664项核对source/preparation/receipt/report身份和141件旧原始artifact stat未变，**未重新打开/解析/hash原流，也未独立再次计算全部operand hash**。实际执行与review层级分开列示，不能把两者写成两遍真实全流验证。历史source review70个合成执行=normal35＋-O35（每模式author28＋reviewer7），不算70唯一case。

## 尚未建立

- accepted operand摘要身份不是DDR逐地址/tag/response握手；相同内容不能证明地址身份。
- retire_result仅验证字段/身份协议，不重建或核对完整16,384-byte result tile内容摘要；没有新的FMA数值或Scalar电路等价。
- 不创建mask/repeat_k/repeat_v/logits实际tensor，不提高softmax FP32批准门限；四非物化节点不能单凭packet PASS无条件签字。
- full29、observer noninterference、Chisel/RTL、硬件周期/active duty/90%利用率仍未建立；本包不包含未执行Chisel候选，不更改canonical任务状态或历史FAIL。

## 复核源码与隐私

三个Python文件及MAPPING_CONTRACT_ZH.md原字节保留；映射契约是**准备期历史文档**，其中“未执行/待执行”不覆盖后来的ACTUAL_RESULT。契约中的原job tag/虚拟DDR base是源模型元数据，不是进程地址或DDR握手日志。其余语义和限制均保留。

可在全新临时目录对本目录运行 `python -B test_independent_packets.py` 与 `python -B test_io_contract.py`（以及`-O`）；只生成合成小fixture，不读取原归档。check_packets.py的真实CLI为显式opt-in，本包不提供可执行私有PLAN或授权。PLAN_PROJECTION只提供roles/hash/资源，不可作为实际路径配置。11个已有公开源引用及1个无完全相同公开blob的MatrixService hash-only见证只供来源核验，不由checker导入。

历史regex测试期待失败的原日志hash仍留在freeze；不把后续合成测试通过说成初次全绿。原source mapping中10个历史Scala/compile/next-step条目仅在原件hash中被保全，不发布其源或未执行候选；公开Python映射20条、实际source witnesses12条明确分层。

绝不上传原始输入、权重/local.npz/remote.npz或其可重构编码、五输入payload、packets、raw events/tensors、私有绝对路径/config/argv/approval内容。固定测试常量和自动生成的合成fixture不是实际权重或原输入。公开内容只限源码、合成测试、hash/pins和必要摘要。
