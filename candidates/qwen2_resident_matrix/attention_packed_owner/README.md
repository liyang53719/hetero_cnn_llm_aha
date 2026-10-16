# 原始 Attention owner 的可选 packed 接入（准备中）

- 已完成：独立 profile2 主机 Matrix 算术微型验证，见 attention_packed_native_evidence。
- 已完成：exact OfficialAttentionOwner 类型保留的默认关闭调度、最终结果槽所有权、实际父 owner 银行 ACK；M1/M2 全部输出与 score 逐字一致。
- 已完成：22 项 normal/-O 回归与独立源码审阅；包含 16 个原始 owner 故障子场景。
- 待完成：完整 Public 接入、Q/K/V 银行供数布线、M16/M128 与完整图验证。

本切片只有 M1/M2 准备入口。新 ScratchBridge 每次外层边沿只调用一次 ParentLoan.tick；它没有新增银行存储。96 字 FP32 panel 为显式拟议 +384B。Q 128字、V/Matrix 256字输入包暂为主机模型寄存缓冲，尚未证明现有物理端口/寄存器映射。没有全块性能或 RTL 通过声明。

原始默认路径通过可逆零 fuzz 补丁保持；可选路径仍由原始 tick、_read/_write、Scalar 与 shared MatrixService 处理工作。非末步只返回接受元数据；末步的实际 service result 持有到匹配 consumer ACK，score 写的标签 ACK 与原始输出写 ACK 都在其之前。最终 selected 非有限检查先于输出写，未选择单元异常不变成全局协议错误。其错误观测延迟是新契约，不能继承原逐步错误周期。


## 复现与边界

    python3 -m unittest candidates.qwen2_resident_matrix.attention_packed_owner.test_client candidates.qwen2_resident_matrix.attention_packed_owner.test_owner
    python3 -O -m unittest candidates.qwen2_resident_matrix.attention_packed_owner.test_client candidates.qwen2_resident_matrix.attention_packed_owner.test_owner

默认冷测试不加载动态库，三个数值/生命周期测试明确 skip。设置 PACKED_OWNER_NATIVE_LIBRARY 为已验证 profile2 库（SHA1ba0b6aa738dd4a409b91adf93cafbcec63fc3c0df1590f9b91cf8f223f54811）后执行全部测试；没有重新编译。可选 PACKED_OWNER_RECEIPT 记录安全源码/库 hash、M1/M2 全 score/output hash 和实际计数，不记录数组。

16 个原始-owner 故障子场景覆盖读错误、外来 DDR 回复后真正回复、selected 溢出、scratch 已接受读/写、写 ACK 同边沿中止、held Matrix consumer ACK 中止、末结果持有期间输出错误/外来/延迟 ACK，以及 acquire/begin/write 未接受时 ready/blocked 两种 reset。两次连续工作及 idle reset 后第三次工作复用同 owner/桥，保持跨工作 serial/generation 单调。

这里的 DDR 是测试物理地址字典与原始 tagged MemoryRequest/MemoryResponse 握手；K/V 尚未合并 PublicKvTransport 缓存命中路由。ScratchBridge 是新的外层接线模型，不能与现有 PublicKvTransport 各自 tick 同一父 owner。下一步必须合并成唯一父边沿调度器。Scalar 仍执行原始同步服务顺序，不构成硬件吞吐率模型；CPU elapsed 也不是硬件周期。完整 Public 21 events、真实输入、原始两套 C++ reference 和原 profile guards 尚未在此新模式运行。
