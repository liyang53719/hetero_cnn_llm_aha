# TEMP：MoE phase-context 源码与实际类型检查

本批不是完整 group 或五块数值验收。原始 Chisel 五 profile 的完整 M128 prefill 数值回归仍为 **0/5**；随后才冻结同源、输入和参考，在同一固定 4096 Matrix、同接口、同 RTL hash 上回放五块。现有任务状态与历史 FAIL 不改。

## 已发生与未发生

- 0602 原实际编译只选择 **19 个生产 Scala 源 → 90 个新 class / 1,454,118 B**，独审确认 19 个 SourceFile、无与 24 个已选依赖类重名；合计 114 类。原外层、native observed、direct reap 都为 0。
- 只到 **typecheck**。本后继没有编译 Spec，没有运行六个计划 RouteGroup case，没有 emit、真实父接线、数值或 RTL。旧 0533 filter BLOCKED、0538 未执行门保留。
- 先前 `moe_ffn_group_r2` 的 wrapper exit 1 / qualified false 与独立解释的三个短 mock case 仍是原版本记录，不转移为此 19 源的控制通过。
- 26.97 秒是采样 CPU，387,706,880 B 是采样 RSS 高水位；27.47176468698308 秒是含 postflight 的 owned-stage wall，不是独立完整外层 wall。完整 pin 循环是源绑定＋qualified 收据，不是保存了每项 observed hash 的轨迹。清理仅证明原 owned group / 已观察身份。

## 本批源码如何选择

新增 16 个普通 Scala、121,656 B：15 个新生产源，另一个 0541 `HostRuntimeLaunchV4.scala` 是 **依赖来源**。生产 19 中另外四个使用 `PUBLIC_REFERENCES.json` 的固定 commit/path/blob：Logical32 consumer、ScalarV2 协议、唯一 FormatV3 协议、Hetero primitive 协议。

`SOURCE_SELECTIONS.json` 明列生产 19 与来源 8 两个不同集合。24 个 selected class 来自其中 **7 个 SourceFile 家族**；第八个 Hetero 来源在生产 19 编译，不贡献 selected24。HostLaunch 的三个类来源不是第二十个生产输入；加入该普通源也不意味着历史命令直接编译了整个依赖文件集。

不得递归编译整个候选目录，不得混入旧 DispatchV1 / LaunchV1、其他同名 phase/context/lease/consumer、旧私有 lease 或重复 Format 协议。`TYPECHECK_IDENTITIES.json` 只提供类 hash / SourceFile / 选择清单，不提供 opaque 类文件。

## 小源复现与依赖恢复

1. 在 `PUBLIC_REFERENCES.json` 固定 commit 的仓库加入本候选原字节。复用该 commit 的公开 composed/ordered recipe 恢复 **515389…** `QwenOwnerProtocol.scala`；bare-root 同名文件不是同版本。`moe_ffn_group_r2/DEPENDENCY_RESOLUTION.json` 仅复用其 source-recipe 说明，**不复用旧 20 类选择规则**。
2. 原 `replay_handoff.py` 设计上的 INCOMPLETE / exit 2 必须保留。按已公开 compile-evidence README、`reproduce_sources.py`、ordered `prepare.py`、`stage_inputs.py` 恢复准确 92-source baseline；完整类重建仍需要已 pin 的外部 20 个 HardFloat 源与官方工具依赖。
3. `assemble_sources.py --repository FIXED_CHECKOUT_WITH_THIS_PREFIX --reconstructed EXACT_ORDERED_RECIPE_OUTPUT_ROOT --output FRESH_OUTPUT` 只验证并复制 19 生产源和 8 来源源，输出两个不同目录与身份收据。它不运行 recipe/JVM/目标，不生成 selected class，不授予运行许可。
4. 独立重建并资格化 baseline 与 HostLaunch 依赖后，仅选 `TYPECHECK_IDENTITIES.json` 的 **24 个符号**，再按 `REPRODUCTION.json` 的 35-token 角色化 scalac 命令编译生产 19。HostLaunch 的来源文件可用于重新编译其三个类；这不是本包已实际执行过的一条自包含重建流水。不得假称同时编译八个完整文件就能替代历史 selected24。
5. 106 JAR 的相对路径、hash、顺序复用 `moe_runtime_merge/ACTUAL_COMMANDS.json.ordered_classpath`，本批逐项比对相同。原两个物理依赖根可重定位，但公开新目录布局不冒称原 argv 路径字节；原 exact token 逆恢复仅由私有 role map 验证。历史 314 JDK pins 与动态 Python/Java/环境闭包并非全套可移植执行环境。新运行仍须另行预算、工具/输入 pin 和监督准入。

## 当前阻断与计划

必须保留 `HISTORICAL_SOURCE_BOUNDARIES.json` 的九项限制，并结合 `PUBLIC_AUDIT_SCOPE.json` 的后续时态说明：源阶段的“未 typecheck”已由后来的 0602 实际类型检查替代，但权限/运行/数值未自动解锁。

真实父层仍须将原 reader、Host/Guard 许可、同事件 postnorm job/receipt、live allocator、完整 transaction/epoch、资源分配和最终 DDR ACK 接通。私有 context/lease 几何一致不等于 authority。**1281 只表示 routed reservoir**；shared/N1/merge/residual 尾部 8 需要另一个未来 1289 父后继，本批不含该版本，也不声称全 phase 已预留或完成。局部 done 不能释放全局 routedDown allocation，不能冒充 shared/N1、九贡献 merge 或全块完成。

原 `UnifiedMoeFfnGroupSequencerV3.scala` 类前两行 DispatchV1 / public Host version8 注释过时，原字节保留：实际是 **Host version 字段 8 bit、值 1**，private phase version 1 / phase 1。这里只纠正文案，不作为历史 type/runtime 故障。

32 lane 仍是共享 Vector/Element 的候选，不缩小固定 4096 Matrix。本批逻辑 32 控制不证明 physical 32-lane II1。持续 issue 还需多在途 tag/credit/scoreboard、跨 tile cache、共享 exact 流水 Div 并保留 sqrt 与逐步 BF16 RNE；不能继承旧 16-lane 或其他有限 leaf PASS，五块必须统一重测。新 reader/tail、1289、Host 后继、权重/参考以及未执行 Specs 均不夹带。

## 本包检查的含义

包装检查只确认原源字节、选择/角色映射、公开引用、Git 树、隐私和纯源恢复 helper。自然触发的 git-payload-guard 通过也不升级任何目标数值或完整块状态。
