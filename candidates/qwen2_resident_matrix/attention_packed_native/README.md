# 原 Matrix 主机模型：显式 packed profile2

## 中文计划
- 已完成：源级后端审计确认 arithmetic exception flags未进入endpoint protocol_error；所有启用cell仍必须计算。
- 进行中：严格零fuzz补丁、冷测试、独立审查；随后一次≤30s微型C++模型编译/数值检查。
- 待办：原Public21/OfficialAttentionOwner调度与实际DDR/loan适配、完整冻结输入数值验收。
- 完整Public packed profile准入关闭；当前不实现RTL，不继承其他profile PASS。

profile2仅通过明确NormalGroup.profile=2选择。QK要求opcode0x23/count8/mask255，PV要求0x24/count1..128/mask15。一个原有accum[5][16][256]资源，context0、clear仅首步、last/finish/emit仅末步；中间返回内部退休，终结结果维持原result→done→owner终结→release债务顺序。profile0/1与默认profile0保持原字节/算术。

QK计算所有16×256=4096启用cell，PV计算所有16×128=2048cell；使用原ordered fmaf ABI。M128实际启用FMA计数应为260,308,992，不是selected-cell行为模型的25,362,432。输出tile16KiB是原服务result，不新增accumulator。

## 异常策略与范围
RetainedMatrix.scala只绑定endpoint协议/数值接口；qwen2_matrix_command_endpoint.sv接收arithmetic flags到局部mflags，protocol_error_o来自merror；front_control的protocol_error来自scheduler。MatrixPipeline只把context/last/protocol/completion错误变成error。因此不能因未消费启用cell的NaN而人为poison整个服务。

本补丁返回全部启用cell原始位，数值非有限不自动成为protocolerror。消费方仍须检查选中值。由于只emit-last，选中值的逐步nonfinite故障时刻尚未与旧owner/行为模型对齐：本次仅资格化有限有效数据的数值，明确selected_fault_timing_qualified=false、full_public_admission=false。测试区分selected与unselected非有限；不能把该差异隐藏成完整owner故障等价。

微型检查使用原Fraction FMA比较所有启用cell、subnormal输入与完整计数，并检查旧profile0/1、错误形状、终结ACK保持。无真实模型权重、无RTL、无完整block运行。独立C++金标准文件不修改。

    python3 -S -B -m unittest candidates.qwen2_resident_matrix.attention_packed_native.test_prepare -q

本目录prepare.compose仅生成全新临时树，固定原源与生成源SHA256；真实编译/载入需单独明确执行，默认冷测试不编译。
