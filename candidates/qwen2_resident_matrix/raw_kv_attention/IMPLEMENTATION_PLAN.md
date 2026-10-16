# 后续最小连接计划（尚未实现）

1. 原始 chisel/continuous_prefill/src/main/scala/heteronpu/continuous/Qwen2Block.scala：仅在 attLocal 的 K read 和 attProbScale 的 V read 分流；保留 packet、attDot、attPVCompute 和所有算术。新增默认关闭接口及显式故障消费抑制，不能把模型侧带当成已有功能。
2. 同目录 QwenOwnerProtocol.scala：在现有 mode-0 memory 仲裁中连接元数据缓存/贷款状态机。先接受核心读，再获得原 Down owner 贷款，再发 DDR miss；匹配 DDR reply 与 raw fill 同步接受。错误路径不修改原债务身份。缓存位仅在 clean fill ACK 后置位；用 raw reread 供数，不加数据影子。
3. 同目录 HostBlockTop.scala：只传播默认关闭参数/既有父模块连接。保持原顶层与核选择；mode0/active 在核心 held completion 和所有请求/ACK/lease 退休前不能切换。不得用全局 Matrix idle 阻塞 Attention 的借用。
4. 上述 patch 必须在当前完整原始 patch 组合后单独应用、单独固定哈希；保留已验证 raw bank 基线。先完成父模块 RTL 生命周期证据，再审查最小消费者 unit。禁止通过强制内部寄存器模拟 retained-A 生命周期。

## 失败状态表

- idle→acquire：接受一个合法核心读，建立 core_pending；若已故障，转 error_response。
- acquire→lookup：实际父模块 grant，retained-A 必须先一拍失效。故障转 error_response，无 DDR 债务。
- lookup：命中转 read_issue；未命中转 miss_req。
- miss_req→miss_wait：仅 DDR 请求接受时建立 ddr_pending；已 offered 请求即使 abort 也保持 valid/身份到 ready，然后排空真实返回。任何无债务的 supplier 回复均毒化。
- miss_wait：外来回复毒化但保留原债务；匹配错误/撤销回复退休 DDR 并转 error_response；匹配成功回复只有 raw fill 接受时才退休 DDR。
- fill_wait：稳定 raw 回复至 matching ACK；clean ACK 提交 valid 后转 read_issue；故障 ACK 排空后转 error_response。
- read_issue/read_wait：raw 同步读及稳定 held reply；核心 valid/ready 消费后撤回回复；若 raw ACK 尚未 ready，转 ack_wait 保留 raw 债务，后续 matching ACK 才退休。故障侧带禁止使用数据。
- error_response：稳定原 tag 错误直至核心消费。
- terminal：关闭新读；保留 mode0/active，等所有债务退休后释放贷款，再允许原 host completion。该门控不依赖 completion.ready。

## 验收界限

本批六文件是模型/来源/短测计划，不包含 consumer RTL。M128真实执行、原始算术数值验收、端到端吞吐、DDR性能及硬件资源结论仍待后续单独测试。父模块已编译/展开的结果不能代替其尚未完成的 RTL 生命周期验证。

## 原始数值消费者的下一步桥接（准备完成，数值未执行）

新增 numeric_bridge.py 测试适配器，不改 OfficialAttentionOwner 的 tick、_attention、_matrix_step、ScalarService 或 MatrixService。只把原 owner 已接受的 K/V MemoryRequest 接到 KvSupply；Q读与输出写仍走原测试 Bus。接受与返回的身份、64B容器顺序保持不变。供应侧故障通过现有 Python local_reset 进入 owner 的 drain，再消费 held reply；这验证 Python 排空契约，不代表 Chisel 已有该故障侧带。

两组短数值比较只用合成 M1/M2：原 DDR 路径与贷款路径分别运行原始 owner，比较输出逐位值、完整 scalar 操作序列、QK dot/score、接受的 Matrix 请求/FMA计数（不比较因传输停顿而改变的 legacy_model_ticks），并复用原 independent reference_attention。加入背压、故障排空和最后 raw ACK/贷款释放前的终端门控。有效数值测试使用有限输入；NaN/Inf原位传输仍由现有26项纯传输测试覆盖。

numeric_prepare.py 和 test_numeric_prepare.py 是普通发现测试，只验证52项已固定依赖及来源，不导入/执行原算术服务。numeric_pins.json 固定当前033ac109来源。数值入口必须显式选择，要求 MATRIX_SERVICE_LIBRARY 及相邻 compile.json，复用原 verified_library 的来源、编译参数、库散列校验。无库时返回 NOT_RUN 且退出码非零，不能用 skip、stub或临时编译获得 PASS。

当前隔离目录没有该库，也没有真正的 git checkout；原 ScalarService 的 source_identity 要求 git HEAD 中 recipe 原文匹配。后续可在已有标准 Matrix CI 的真实 checkout 与已验证库上下文中单独扩展短测，先审查再运行，不绕过源检查。此批不创建新工作流、不启动编译、不上传合成数据或完整算术轨迹。只允许输出状态和计数摘要；不能据此宣称 M128、公有模型数值验收或硬件时序通过。

## 既有 Matrix CI 的最小数值扩展（已准备，尚未运行）

仅在 .github/workflows/qwen2-matrix-interface-frontend.yml 原有 job 中，普通 contracts 测试之后、长 Scala 检查之前，加一次 run_attempt==1 的 run_numeric_ci 调用。继续复用既有 build_shared_matrix_recipe 产生并通过 GITHUB_ENV 导出的库/回执；wrapper 只调用 from_environment 校验，不调用 build。保持原触发路径、一个 job、20分钟总时限及既有编译步骤。最近已观察到约17分钟的总运行，因此新增 wrapper 的120秒总预算包含最多5秒清理（子进程至多114秒并扣除准备时间，另留1秒回执写入），不延长 job 时限；实际余量仍须以本次日志确认。

新增52输入检查包含严格共享库构建验证器、原始 native 编译闭包及已测试的进程组清理 helper。运行前后冻结原始依赖、adapter/runner、owning workflow、library 和 compile receipt 的散列；发生漂移不能 PASS。复用 start_new_session 及 SIGTERM/TERM/KILL 的全组清理，不重试、不增加 native 编译。

只有 work/raw-kv-attention-numeric/summary.json 与 source_hashes.json 加入原有 artifact 的显式清单。子进程原始输出保留在临时目录，绝不添加到既有递归上传路径或打印到日志。成功必须同时有 M1、M2 及故障排空的固定摘要，缺库、超时、异常、非零返回或摘要不匹配均不是 PASS。输出仅为固定状态/计数与来源散列，不上传数据、权重、完整标量轨迹或绝对本地路径。
