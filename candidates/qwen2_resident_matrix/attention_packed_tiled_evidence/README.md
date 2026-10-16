# M17/M32 实际分块 Public transport 验证

已完成：同一原始 OfficialAttentionOwner、实际 PublicKvTransport、同一 ParentLoan/Banks 和既有 packed native ELF。每个 case 是一个真正多行 Attention job；所有启用的 Matrix cell 都执行。M17/M32 全部 score/output 与原始 owner AST 的 Fraction 参考逐位一致。

M17：成功 + key16 panel abort + 匹配 DDR 错误，三项共34.360秒外层时间；成功执行7,704,576 FMA、2034步、250个joined结果、864次scratch事务。两个故障均停止query16输出发布，并清空已接受债务。

M32：成功，60.436秒外层时间；执行21,037,056 FMA、5664步、640个joined结果、2304次scratch事务。两种成功case在query16/key16重载时均保持真实raw response七条ACK停顿边，检查同一PV group/tag/index与payload身份；owner和parent边数相等。

内部90秒、外部95秒；实际均exit0，清理完成，187项源码与ELF执行前后相同。复用既有ELF，没有重新编译。EVIDENCE保存两个原始结果、两个外层退出回执和执行pins的精确字节/hash。原始文件可通过 PACKED_TILED_RECEIPTS 环境变量独立核验。

保留显式384B panel资源与拟议控制连接。软件tick不是硬件周期；完整21事件Public程序、M128、RTL及80/90%利用率不由本项证明。全M16业务程序的独立PASS也没有被移植成M128结果。

已完成：实际执行、全部score/output参考比较、源/库postflight、冷证据测试。已完成：独立证据复审（2项 normal/-O 外部原件测试，零跳过）。待办：显式完整M128程序准入与预算审查。

测试：python -m unittest candidates.qwen2_resident_matrix.attention_packed_tiled_evidence.test_evidence，另用python -O重复。
