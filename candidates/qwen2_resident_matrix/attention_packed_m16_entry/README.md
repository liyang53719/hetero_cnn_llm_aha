# M16 原始 Public21 入口衔接（进行中）

- 已完成：44 项 normal/-O 冷测试；三个原始入口层的 source-map 相同，观测器固定映射通过；原始 Public 执行循环/终态与比较函数的 AST 投影检查通过。
- 已完成：真实 be00 Git 克隆中的原始 ScalarService、OfficialAttentionOwner、共享 Dense/Matrix 和 ReducedPublicExecution 构造检查。仅 libc 浮点环境探针及明确的 Matrix 控制桩；0 个数值 job、0 个 parent tick、0 次 payload 读取。
- 已完成：另行归档的真实 native M1/M2 十字段观测已通过；该小样本不继承完整程序成功。
- 已完成：两根目录的资产准入、真实 reference launcher/调用方退出回执衔接；真实原始 prepare 与 verify_snapshot 已通过，13个输入角色，未启动数值 job。
- 进行中：本入口和单次有界启动器的独立复审。
- 待办：冻结完整启动器并通过复审，再申请900秒内部/930秒总期限的 M16 原始程序运行。

## 必须保留的边界

使用原始 ReducedPublicExecution、PublicFrontend、HostControl、DenseReductionOwner、OfficialPrefixOwner、OfficialAttentionOwner 和同一 Matrix/Scalar。原始21事件、17个job、ACK后的输出、后置 reference gate、固定算术比较和27个 assigned 官方观测门限都保留。full29仍不成立，不能用独立 Attention PASS 继承完整程序成功。

旧树和旧默认路径保持原样；单独组合树必须显式选择 packed M16、fresh reference 和 raw KV。source-map 扩展同时覆盖最内层 check_fullgraph_numeric.runtime 的传递 imports、official runner、reduced runner、packed profile 和观测器的固定映射。不能只更改顶层映射。

严格 ELF 原件的 argv 仍指向真实构建目录。library_origin.verify 校验原件 hash、精确原 flags/四源、当前 compiler、ELF，以及新执行树四源完全相同；不会把原件路径或时间改写为新构建。最终契约还必须固定本 verifier、origin receipt/ELF hash 和全部执行源。当前函数单独成功不代表完整准入。

资产来源分开：be00 原始13张量/native16只读核验；新 M16 arena 与 sequential/block-pair 输出必须新生成。native16是明确复用的已有执行，不能声称重新运行；M128 ASSETS/SETUP 不能改标签。native独立QK参考不能替换硬件16stripe/fold算术。所有 reference 数组保持全程序终态前关闭。

本目录提供显式 M16 资产/源码准入及原始入口适配；外部进程监督启动器另行冻结。authorize_run 要求同一 PID、单次 attempt、精确 source-map、真实 be00 Git 上下文和从同一起点计算的924秒工作/930秒总期限。该上下文不是已完成数值运行的证据。

已执行 reference 准备契约 de460188 的原始回执由 provenance.json 单独固定；后续便携发布模板不被视为已执行来源。两套原始 C++ reference 为新生成 M16；已有 native16 导出及严格 combined ELF 明确复用。

完整程序仅经 Python API 显式 enable_packed=True、fresh_profile=True、enable_raw_kv=True 启动；旧 CLI 缺少选择参数，失败关闭。完整数值、RTL及性能达标仍待验证。

## 冷检查命令

`python -m unittest candidates.qwen2_resident_matrix.attention_packed_m16_entry.test_prepare candidates.qwen2_resident_matrix.attention_packed_m16_entry.test_admission candidates.qwen2_resident_matrix.attention_packed_m16_entry.test_views candidates.qwen2_resident_matrix.attention_packed_m16_entry.test_library_origin candidates.qwen2_resident_matrix.attention_packed_m16_entry.test_preparation_receipts -q`，另用 `python -O` 重复。

`cold_construct.check()` 只适用于真实的原始 Git 克隆加精确组合源；它保留原始 ScalarService 的 Git 与浮点环境检查，不能以空目录或伪造 Git 元数据替代。它会接受原始 metadata frontend launch，但不会推进 owner、读取任何模型 payload 或执行数值算术包。
