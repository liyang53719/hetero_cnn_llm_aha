# GDN Execute32 接入计划（尚未接入）

基线：兼容源 8eb141f0cb3d9fab16f74c2b1e2704e3b2f966ab 中的原 ExecuteV8；parent 当前 main 是 90f71b6198a6fc1bf54683b0cf87bb5d37240e9b。本候选只新增独立 leaf，不修改任何现有选择或批准。

## 当前真实路径

路径相对仓库。F 表示 candidates/fresh_original_top_recovery_20261028/source。

1. F/GdnRuntimeChunkExecuteOwnerV8.scala：V5 ordinary wrapper 内部仍为 V2 Vec16。
2. F/GdnRuntimeChunkLeafCollection.scala:75–110：唯一 ExecuteV8，DerivedVector=0、ExecuteVector=1。
3. 实际 Kernel 是 candidates/p0_resident_observation_20261030/source/QwenOwnerProtocol.scala:158,275,551–575，不是 F 下同名旧副本。
4. F/HostRuntimeChunkProtocolV9.scala:8–19：跨 Kernel 边界两个16lane client。
5. 实际 Top 是 candidates/moe_router_score_observation_20261030/source/HostBlockTopV4.scala:52–64,174–187。
6. F/HostRuntimeChunkWiringV9.scala:158–175：真实 router/fabric，retains request.fire 时的返回归属。
7. F/UnifiedMoeSharedArithmeticAdapterV5.scala:235–250：slot10只填低16，物理高16为+0；低16结果返回。
8. F/UnifiedVectorElement32BankV4.scala：唯一32lane bank。不能因换宽client再实例化一个bank。

已有 prefill_supply_overlap_20261103 候选只改 Dense/iDMA；与本leaf没有重叠实现。未来若叠加，必须从实际选源链组合，而不能编辑未选中的同名文件。

## 必须闭合的新契约

- 增加显式 Chunk32 payload/return 路由及独立 authority/client slot；旧 ordinary16 ABI 与 RMS32 domain 不变。不能借 RMS slot11：它只承认 RMS32 authority，且不接受 Chunk 渐进 Add。
- 编译期 opt-in 默认关闭。开启时替换 ExecuteV8，不同时保留两个 execute 实例。Derived 保持原16lane route。
- 新slot只能仲裁到原唯一BankV4。请求policy只允许0/3/4，format必须multiply=false且B全0；identity必须从真实Guard+RawPrep lease生成，不能信任raw payload。
- 同步修改 Collection、实际Kernel、HostRuntimeChunkProtocolV9、HostRuntimeChunkWiringV9、实际Top和AdapterV5的宽度、held-offer、返还owner及drained计数。
- 原memory仍走五个client和单17-client hub。每个64B beat保留tag、权限检查、request.fire、response和ACK；不可用count公式替换实际事务。
- 新selected-source及generation contract必须显式加入。现159-source legacy/address选择不能悄悄覆盖；外部122ports/4096MAC/唯一Vector32最终需真实Top elaboration与resource inspection。

## 精确计数，不能把整个Chunk除2

令 H 为valueHeads，M为tokens，C在M128时为2，否则为1。

- Scalar不变：H*C*((H==32 ? 832 : 64)+2209)。
- Derived仍是 H*C*4704，其中每head/chunk 2144 Add、2560 Mul。
- 新Execute32是 H*C*329472 + 4*M*H。
- 两者合计 H*C*334176 + 4*M*H。

H16/M16、H16/M128、H32/M16、H32/M128 的完整Chunk vector exact值分别为 5,347,840、10,701,824、10,695,680、21,403,648。它们只是未来实际授权/退休必须核对的精确操作数，不是现有授权。

当前 Wiring :85–95仍mint旧 H*C*663648+8*M*H；:228–240与adapter :369–375按实际返回检查。只换leaf会被正确拒绝退休，不能通过放宽成功计数解决。

## 还缺的动态验证

- 真实FSM高半read回压、write第二ACK停顿、跨row solve先前行全部ACK、stale/wrong-tag和错误结果隔离。
- 原BankV4的policy0/3 signed zero、gradual underflow、flags和policy4 ties/overflow，先Mul后Add不融合。
- 新route/lease的held offers、fault drain、exactly-once返回及终端held。
- 新Top同一硬件下五profile M128的完整数值/周期验收；理想、压力、目标内存分别计量。

本轮只做到真实叶编译及CHIRRTL和独立小模型，没有动态Chisel/RTL仿真。GDN直接影响P1/P3，其余profile必须继续共享同一硬件且通过回归，不能按profile重elaborate。
