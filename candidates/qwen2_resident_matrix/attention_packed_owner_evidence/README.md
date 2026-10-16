# 原始 owner packed M1/M2 接入证据

- 已完成：使用已资格化 profile2 动态库，原始 OfficialAttentionOwner M1/M2 的全部 output 与原始 Fraction oracle 和默认 native owner 逐字比较；全部 score 与 Fraction oracle 逐字比较。
- 已完成：22 项 normal/-O，1.620/1.684 秒；16 个 owner 故障子场景、两次连续作业与 idle reset 后第三次作业均通过。
- 已完成：本安全证据切片独立复核，2 项 normal/-O 原件验证均通过，零跳过。
- 待完成：与 PublicKvTransport 合并为唯一父边沿、真实完整 Public 输入和 21-event 验收，原始 C++ 双 reference 不变。

本次重用动态库 SHA1ba0b6aa738dd4a409b91adf93cafbcec63fc3c0df1590f9b91cf8f223f54811，没有新编译。执行 pins 为 fd272e2649fa5655913aa7bcf6187abb3f7901cbe9719ec6a1c9e326eb6f5784，收据绑定全部123项源码身份。M1/M2 对比分段用时为0.6723/0.7125秒（normal/-O各自包含两个shape），不是硬件周期。

M1：98个实际 Matrix steps、14个最终结果及done；397312个全启用单元FMA，3072个有用selected FMA。208个 tagged DDR读、96个输出写/ACK，6144输出字节。1520个 owner边沿对应恰好1520个实际父 owner边沿。

M2：198个实际 steps、28个最终结果及done；798720个全启用FMA，9216个有用selected FMA。528个 tagged DDR读、192个输出写/ACK，12288输出字节。3365个 owner边沿对应恰好3365个父边沿。

所有最终 Matrix 数据保留在真实 MatrixService result 槽；score scratch 和输出写有显式 tagged债务，只有成功匹配ACK才能发布。异常、外来回复与延迟回复都不能提前释放，也不能形成成功终态。调用者负责实际 shared Banks 每边沿唯一调用；完整 Public 合并尚未执行。Q/K/V 输入包和+384B panel仍是显式拟议寄存资源；尚未建立硬件供数/时序或利用率。

复核命令：

    python3 -m unittest candidates.qwen2_resident_matrix.attention_packed_owner_evidence.test_evidence
    python3 -O -m unittest candidates.qwen2_resident_matrix.attention_packed_owner_evidence.test_evidence

PACKED_OWNER_RECEIPTS 可指定原始安全收据目录，执行额外原件核对；未指定时明确skip。JSON只含hash、计数、布尔与安全日志，不含张量。
