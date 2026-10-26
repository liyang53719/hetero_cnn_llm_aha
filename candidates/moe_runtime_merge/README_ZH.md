# 固定资源 runtime MoE 合并控制叶子（不是完整 block）

## 结果
- 新固定结构 HeteroRuntimeMoeMerge：16 route slots、10 bit expert、512 bit 结果缓存，不按模型 elaboration，不增加/缩减 MAC。一个 DUT 无 reset 执行 legacy9 → expert9 → legacy16 → expert8；4/4 Chisel/Treadle 测试通过。
- 专家模式锁存统一 descriptor.mlp==1，按 expert ID 递增合并；共享 sentinel256 即使首先装载也最后输出。legacy 只保留兼容，不是官方数值等价。
- 测试验证 OOO 回传、busy 时外部配置扰动、held dispatch/merge、每条结果仅 fire 一次消费、12 输入负例、重复/越界回传 drain 后失败、完整16槽同拍返回。权重/结果都是不透明身份数据，本测试没有 BF16 运算。
- 四份测试 low FIR 完全同 hash。第一次官方 firtool 1.62.1 直接读取 Treadle low FIR 失败（validif parser）；原失败日志仅本地保留；公开结构化诊断/receipt/SHA绑定。未编辑 IR；复用同次已验源和 classes，通过新增小入口 ChiselStage.emitCHIRRTL 原生生成，再用相同官方工具成功得到一份 SV。不是 SV 仿真，也不是综合/时序/PPA 验收。

## 集成边界
本包仅候选，INTEGRATION.patch 将同一实现新增到公共 primitive 源目录；尚未应用/绑定统一4096 top。旧 HeteroMoeRouteDispatch 保留的不兼容历史 witness 不变，禁止同时接入两套模型专用 datapath 冒统一硬件。调用方唯一共享实例的 profile→policy 绑定、64-bit transactionId/单 active job/drained fence 必须实际集成，不能任意由 host 选择 legacy 绕过官方次序。旧 result bundle 仅有 routeTag，无 epoch；当前叶子无法分辨跨 job 的同 tag 陈旧返回。clear 具有破坏性优先级且不门控当拍握手，测试只覆盖初始化clear，不是安全忙时abort。父层必须先禁止新任务、quiesce/drain全部已发返回及下游贡献，绑定当前transactionId，再在没有在途握手的边界clear。

PROFILE_MAPPING.json 固定后继 typed gateway 的 BF16 权重编码：低16为已物化 BF16 原 bits，高16为0；高位非0拒绝由 gateway 实现，本 opaque primitive 不实现。真实共享 scalar consumer 仍需验证 BF16乘权、每 expert BF16加和、共享最后，并连接完整 L0/L3 数据路径；本包不把软件或 Torch 数值 witness 当硬件数值通过。

## 复现
以 `ACTUAL_COMMANDS.json` 的角色化命令为入口：将 REPOSITORY/CANDIDATE 指向校验后的源根，两个 dependency role 指向只读 jar 根，JAVA21/FIRTOOL 指向核验后的工具，为每阶段分配新输出根；按 ordered_classpath 顺序展开 role 后以冒号连接为 PINNED_CLASSPATH。依次执行 commands.compile、commands.test、commands.chirrtl_compile、commands.chirrtl_emit_chirrtl、commands.firtool_success；原始失败命令另存 commands.firtool_lowfir_failure 供问题复现，不必先失败才能走原生CHIRRTL路径。所有原始机器绝对路径/原log仅本地保留，公开用 role+relative projection 与原证据SHA绑定，不把投影说成原始字节。

ACTUAL_COMMANDS.json 保留本次 argv 的角色化投影及有序106个 jar SHA256、heap/RSS/CPU/wall/output 上限。可移植重放：使用 pinned Scala2.13.16/Chisel6.7.0/plugin/Chiseltest6/ScalaTest3.2.19 的 jar-only classpath，先校验 SOURCE_PINS；首次 fresh classes 编译恰好四源（原 HeteroOperatorPrimitiveProtocol.scala、原 HeteroSelectionMemoryPrimitives.scala、本实现、本 spec），执行 org.scalatest.tools.Runner -s gemmini.HeteroRuntimeMoeMergeSpec。之后只编译本 EmitRuntimeMoeMerge 入口到另一 fresh classes，classpath 加上首次已验证 classes，执行 gemmini.EmitRuntimeMoeMerge NEW.fir；最后官方 firtool 按保存 argv 读取新文件。不得将失败 low FIR 手改为可解析版本，亦不得将不匹配旧 classes 作为源码测试证据。

预算：初次编译/测试各 heap512MiB、RSS1GiB、单核 CPU120s/wall180s；emit 入口编译/发射各 CPU60s/wall90s；firtool CPU60s/wall90s/RSS1GiB/AS4GiB。无下载/权重/完整模型执行。原 fail 和实际新成功均在 SUMMARY 中，公开包不含大 SV/数据/机器绝对路径。
