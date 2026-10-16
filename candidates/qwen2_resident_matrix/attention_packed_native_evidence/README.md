# Packed Matrix profile2 微型原生模型证据

## 中文计划
- 已完成：独立源码审查、4 项冷测试 normal/-O；单次有界主机 C++ 编译及微型运算验证。
- 已完成：冻结原始安全收据、编译参数、编译器/动态库 SHA256、97 项执行源码身份。
- 已完成：本证据切片独立复核，2 项证据测试 normal/-O 均通过，原件验证零跳过。
- 待完成：原始 OfficialAttentionOwner 的可选 packed 调度、真实 DDR/共享银行供数、延迟 selected-fault 发布围栏和完整 Public 数值验收。

2026-10-16 的单次检查返回 `PASS_TINY_PACKED_NATIVE_MODEL`。编译及检查共 0.756322422 秒，编译完成于 0.430385062 秒；Python 主进程峰值 RSS 19,252 KiB（不包含编译子进程峰值）。外层使用 27 秒 TERM 加 3 秒 KILL 清理上限。此结果是主机模型运算测试，不是 RTL 或全块性能测量。

采用 g++ 14.2.0，完整参数见 EVIDENCE.json。QK8 计算全部 4096 个启用单元，共 32,768 FMA；PV3 计算全部 2048 个启用单元，共 6,144 FMA。这两项逐字比较独立 Fraction FMA oracle，包含负数、小 BF16 次正规数与负零。PV128 常量边界检查 262,144 FMA 和全部启用输出。另检查原 profile1/默认 profile0、held result/done、提前释放、错误 shape/context/clear/emit，以及 selected/nonselected NaN。

现有端点没有把算术异常 flags 接入 protocol_error；本 profile 同样不把未选择单元 NaN 变成全局协议错误。最终 selected 值的异常发布时间与 owner 发布/排空逻辑尚未资格化；因此 `full_public_admission=false`、`selected_fault_timing_qualified=false`。默认 profile0/1 算法及独立完整 C++ goldens 未修改。没有发布动态库或张量。

可重放的冷证据检查：

    python3 -m unittest candidates.qwen2_resident_matrix.attention_packed_native_evidence.test_evidence
    python3 -O -m unittest candidates.qwen2_resident_matrix.attention_packed_native_evidence.test_evidence

提供 `PACKED_NATIVE_RECEIPTS` 指向原始本地收据目录，可额外验证三个原始文件和动态库哈希；否则该外部原件检查明确 skip。
