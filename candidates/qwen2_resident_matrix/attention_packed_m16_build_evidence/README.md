# M16 严格 combined ELF 实际构建记录

- 已完成：单次授权构建，原始严格四源 verifier 通过，exit0；外部0.619492秒，构建及核验0.575138秒。
- 已完成：安全回执独立复审、2 项 normal/-O 原件核验测试，零跳过。
- 待办：M16 资产/观测器/完整入口审核，以及另行授权的实际数值执行。

这是新构建的同一 Matrix+SiLU ELF，不是旧 M1/M2 tiny library。Matrix 含已审核 packed profile2，原始 SiLU 源和原始严格编译 flags 不变。174 个已组合源身份前后相同。没有执行数值 job、完整 Public 程序或 RTL。

ELF SHA256：a31f0cd5fd8184543ff489cc1cb2978d6f049c09eaa3edb24698e765360d4ff8。
编译回执 SHA256：76ca454ca9433859b2cd517908759b26a5f311319efad9e780592c86a7d093ae。

外层 GNU timeout 在31秒发送 TERM，4秒后 KILL；原始编译器30秒 timeout 保留，子进程/编译器继承同一监督进程组。实际未触发超时。安全 JSON 只保存来源/工具/ELF 哈希与标量时间，不包含权重、张量或私有工作路径；原始回执保持原样私有保存。完整原件核验测试通过 PACKED_M16_BUILD_RECEIPTS 指定原目录，仅读取，不加载 ELF。
