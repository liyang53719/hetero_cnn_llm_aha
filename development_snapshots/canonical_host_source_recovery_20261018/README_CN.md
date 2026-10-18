# Host 项目源码恢复候选 v2

状态：SOURCE_ONLY_RECOVERY_CANDIDATE_V2，待独立复核，未提交、未上传。

v1 保持 HOLD 原样保存。其测试导入项目模块时可能先读取合法污染 pyc，随后原源码 hash 测试仍通过；这不满足“执行的就是已核源码”边界。v2 仅修复测试载入器、增加对应负测和更新说明/hash/manifest；recover.py 与 22 个恢复源均未改字节。
本候选在旧五个快照之外独立组装，旧快照与仓库未修改。

## 现在真正能做什么

从固定发布源码恢复 22 个逐字文件（21 个 C++ 项目源码与 1 个 Python hold 契约，共 361697 字节），建立明确的相对引用关系、逐文件来源 pin 和一个 Python 标准库冷循环。没有重写、替换或补齐缺失 Host 接口。

源码基线：仓库 liyang53719/hetero_cnn_llm_aha；commit 9b2ea5490c5d01870d1b8d953f3dad83cd245c9e；tree ca48664f17b4df0024e8e688dd2a4c0168f0cb9f。SOURCE_PIN.json 保留五个审计包路径及 22 个文件的原仓库路径、组装路径、字节数和 SHA-256。恢复命令验证所选源码字节，不调用 Git，也不证明整个仓库树。hash 不是签名。

source/include 保留可复用的 bridge 八个头、silu_observer.hpp 和独立 axi_protocol.hpp；source/pc0 与 source/startup 保留各自同名文件，不能扁平化；source/hold_contract_cold.py 原样保存。所有源码与当前已发布快照字节相同；旧快照已有 include 重定位不被改写，也不被描述为更早原始字节。

## 可直接重复的小闭环

在本候选目录执行（只需 Python 标准库）：

    python3 -I -S -B recover.py verify
    python3 -I -S -B recover.py closure
    python3 -I -S -B test_recovery.py
    python3 -I -S -B -O test_recovery.py

从固定恢复仓库重新组装到一个不存在的新目录，再检查新组装件：

    python3 -I -S -B recover.py assemble --repo ../hetero_source_recovery_20261018T0747 --out ../host_project_sources_reassembled
    python3 -I -S -B recover.py verify --source ../host_project_sources_reassembled
    python3 -I -S -B test_recovery.py --source ../host_project_sources_reassembled
    python3 -I -S -B -O test_recovery.py --source ../host_project_sources_reassembled

--repo 与 --out 是调用者本地位置参数，不写入 payload。输出目录必须新建且位于仓库外；已有目录拒绝覆盖；任一源字节不符先拒绝，尚不建立输出。只复制所列源码，不读取权重、模型、旧运行环境或系统目录。重复执行请使用另一个新的输出目录。测试用临时目录验证组装与拒绝路径，退出即清理，不执行任何 C++。

19 项冷测覆盖：确切文件集合和源 hash、Python 解析、独立 AXI 头文本、37 条 literal quoted include 边、同名 ledger 的局部解析、可重组装、拒绝覆盖/写进仓库/源篡改/额外源/不安全相对路径；以及 synthetic hold 的首样本/保持期新请求、债务、累计活动、payload 稳定、真实 valid+ready ACK 条件、ACK 样本和释放后拒绝。另外验证正常/-O 对应的合法污染 pyc 不会供应项目执行代码，以及源字节改变在执行前被拒绝。测试载入器一次读取项目源，按 PROJECT_SOURCE_HASHES.json 先核同一 bytes，再直接 compile/exec，不通过项目 SourceFileLoader。污染 pyc 只在临时副本创建：旧载入器正对照证明缓存有效且会执行无害模块属性 marker；新载入器不执行该 marker。测试不把 Python 标准库导入纳入项目源码 hash 范围。使用 unittest 显式检查，优化模式不会删掉断言。PROJECT_SOURCE_HASHES.json 仅散列 24 个项目源文件（22 复制源及两个新脚本）。

## 引用闭包的实测边界

五包的所有 21 个 C++ 项目文件均已纳入；观察 taps 的 6 个 Scala 与 3 个 patch 不属于本 C++ 引用组装，仍在原发布包，未复制。SOURCE_CLOSURE.json 可由 closure 命令逐字逻辑复算：37 条 literal quoted include 中 20 条解析到组装源，17 次引用仍涉及以下 9 个未附名称。

- 项目源码缺失：host_memory.hpp、host_ports.hpp、sink_stream_bridge.hpp
- 生成模型未附：VHostBlockTop.h、VHostBlockTop__Dpi.h、VHostBlockTop__Syms.h、VHostBlockTop___024root.h
- 外部运行时未附：svdpi.h、verilated_sym_props.h

前三个文件名在固定仓库追踪文件中均不存在；针对 HostMemory、HostPins、PhysicalObserver、WritePermit、CanonicalSink、CompletedCanonicalSinkStream、Sha256Cpu 的项目源码内容检索只找到使用点，未找到可逐字恢复的对应实现。帧流契约实现也没有恢复。已有其他测试中的自造输入/权重/参考流程及不同 eval 调度不能拿来冒充此 HostMemory/loader。缺失项应继续拒绝，不能用 stub、空类型、常量事件或另一个模型补成“通过”。

引用扫描仅覆盖冻结源码的 literal quoted include 文本与约定的局部目录、include/ 查找次序，不求值预处理器、不检查系统尖括号 include、不执行 C++ 语义分析，也不建立可编译闭包。缺失头将来还可能引入更多依赖。generated_binding.hpp 是已发布的项目适配源码；不是生成模型实现。

## 中文恢复清单与停止条件

- [x] 固定已发布 commit/tree；旧五包保持原样。
- [x] 22 个项目源逐字复用，来源和 hash 可复核。
- [x] 单独保存 startup/pc0 的同名 ledger；可从固定仓库重新组装。
- [x] 小型 source/cold 循环正常与 -O 均检查；结果只说明当前源码/合成契约。
- [ ] 找回原 host_memory.hpp、host_ports.hpp、sink_stream_bridge.hpp 及其逐字来源/递归项目依赖；找不到则停在 SOURCE_ONLY，不凭使用点猜实现。
- [ ] 在另行授权、受审的依赖门恢复真实生成模型、运行时和绑定闭包；本候选不执行这一门。
- [ ] 完整 PhysicalObserver 的 11 方法、其他 owner、prefix、统一 low/high 调度及 full Host admission 仍未闭合；保留 fatal 行为。
- [ ] 新 actual 运行须另行从 reset 和完整真实输入开始；不能续接丢失进程，不能继承旧 actual、full27 或终态资格。
- [ ] 17 owner / 21 completion / 27 capture、B 退休、全域债务和活动冻结、actual 字节及两个参考数值比较仍需独立证据。完整 block RTL 仍为 0/5。

## 丢失事实与证据分层

最后一次 N0 原会话断连前观察停在 row 28、cycle 646947。终态未知；不能据此报告通过、失败或进程已完成。恢复后的环境中，未发布 full27/actual 产物缺失，已发布 source 产物完好。现在的 source/cold 是恢复后新跑结果，不是旧运行收据，也不能恢复旧 RAM/寄存器 checkpoint。

这与已发布 PC0 历史源码中的旧 2000000 cap / NOT_COMPLETED 记录是两件不同事实。本候选保留 PC0 原字节，不扩 cap、不启动运行。

axi_protocol.hpp 只做有限源码文本检查；未编译、链接或执行。Python hold 是小型合成控制契约，不是 C++ 或 RTL 的行为证明，类型注解不提供外部数据类型认证。没有 C++/EDA/RTL/native/model 运行、权重、输入/参考数组、actual 文件、生成模型、二进制、系统/工具链清单、系统文件 hash、网络访问、Git commit/push 或上传。
