# Packed M16 原始 Public 程序准备

- 已完成：独立 M1/M2 transport 验证；本目录复用其原始 owner、共享 parent/banks 和单次 parent tick。
- 已完成：M16 类型化选择、严格 Matrix+SiLU 同一 ELF 源码闭包、6 项冷测试 normal/-O 与独立复审。
- 进行中：新 M16 资产准备、packed 观测器和完整入口的来源衔接。
- 待办：新 M16 arena/两份独立 C++ reference、packed 观测器与完整入口冻结；审核后的准备执行；900 秒内部/930 秒外部原始 Public21 数值执行。

本切片没有完整数值启动权限。`authorize_full_numeric` 无条件拒绝。没有编译、下载、reference 执行或完整程序运行结果。

## 最小源码变化

独立补丁只扩展 PackedSchedule 的规范整数 M16 准入，保持后续 QK 8 步、16 项 fold、BF16 边界、顺序 softmax/PV 和 scratch ACK 语句不变；增加精确 M16 profile 类型；向原始 suffix 的 Attention 调用传递可选 profile。缺省参数保留旧调用路径。M128 不准入。

新 profile 在任何 owner/银行改变之前验证原始精确类、空闲债务、完整已组合源和新鲜严格编译回执。combined ELF 使用原始 dense_silu.build_library/verify_library、原始两个 translation units 和四文件闭包；仅 Matrix translation unit 包含已审核 profile2。原始 SiLU、独立 C++ goldens 不改。旧 M1/M2 tiny ELF 不是完整程序 combined ELF。

`library.build` 是供将来受限子进程调用的函数。外层监督器须对该子进程和继承其进程组的编译器统一 TERM/KILL/reap，外部预算覆盖原始编译 timeout30 秒及清理；此切片没有监督器或执行命令。原始编译回执保留实际路径、flags、compiler、四源和 ELF 哈希。

既有 be00 私有资产只能只读核验。其 M128 ASSETS/SETUP 不能改标签充当 M16；pair-generated native16 必须通过明确新来源适配器核验。完整 Public 的 21 completions、17 jobs、27 assigned/28 observed/full29=false 范围必须由实际新运行建立，不能继承 Attention 子链成功。

新物理 register mux、显式384B panel 和输入 feed 对应关系仍是候选软件控制模型范围；没有 RTL、硬件周期或80/90%利用率结论。
