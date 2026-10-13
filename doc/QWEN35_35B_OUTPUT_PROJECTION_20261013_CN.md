# 35B L0 输出投影 K4096 / N2048

## 当前范围

- 基线91f41da5已完成同次真实RMS至32头gatednorm的M16/M128执行及同输入诊断，九条原CI闭环。完整block仍open。
- 本批独立审计官方单次 out_proj：BF16权重[2048,4096]，无bias。仅取shard13指定16MiB，固定header、原revision、206范围及manifest哈希；不下载专家。
- 官方完整[1,M,4096]输入必须是前批实际gatednorm输出。不同K/N的已验归约不代替本次校准。
- 实际接线已在同一前缀调用中完成，消费真实norm producer对象，保留同Matrix/owner/TypedMemory；校准读取留存raw只用于独立参考。

## 独立原形状校准与所选策略

- M16/M128五配方独立校准完成。四个独立K1024 high-first，三个FP32 Add按左折顺序，最终BF16 RNE，两档均与官方逐bit一致。balanced分别1/5词差；ascending分别16/158词差，max3/4ULP。
- 因此选择显式四段streaming A与两槽chained-sum路径，优先实现官方匹配控制，不先长跑已知不同的ascending备选。既有seeded helper小门13项通过，仅备选且保留work，不进入主接线。
- 每个N≤160窗口依次P0→slot0、P1→slot1、sum01→slot0、P2→slot1、sum012→slot0、P3→slot1、sum0123→slot0、最终BF16 drain。
- 片上A仍16×1376×32=704512B，每K1024 slab只用低512 words/bank=262144B；slot0/1仍各81920B。不新增slot、Matrix、Vector或tensor缓存。
- A读地址必须base+row×8192+block_begin×2+beat×64，实际DDR握手送入localK；B仍globalK×N。旧默认K≤2048/two-partial契约保持。
- 新sum租约允许sealed sum0+fresh partial1、每步新identity，真实lhs/rhs响应接受后才能覆盖。原默认只接受两partial，不将sum伪装partial。
- 此路线不seed、不申请1MiB DDR prefix；独立NoPrefixWorkspace只用于受限streaming窗口验证，不能用于普通seeded Dense。
- 输出M16 65536B / M128 524288B。已核末ACK、终态、输入身份与旧state/history不提交；当前路线没有seed ACK。
- 软件事务ticks、源级MAC预测均不代替硬件完整周期或占空比。下文两档已取得O原形状数值及实执行计数。

## todo / ongoing / done

- done：原源码/shape/seeded接口/资源审计；O-only payload普通3项及优化3项小门；下载16MiB并校验固定manifest；完整两档官方/C五配方校准，13项参考小门。
- done：四段streaming A地址与sum租约、coordinator合成实际控制小门；上游同owner资源回归；同次M16/M128实际链终态及独审。
- done：最新源码643项/67套/195源零skip冷门，源前后不变；计划清单338项通过。
- ongoing：小批发布及精确提交原CI闭环。
- todo：O后残差/postnorm/MoE及完整block联合提交；此批不混入。

## 新控制小门记录

- chained-sum 14项：真实Vector16三次左折、M128/N160端口、旧两partial同wrapper兼容、跨ng有限identity复用、held operand/result、overflow、abort/reset及RMW排空。
- streaming owner 10项：真实strided DDR→RMW→A fence、局部SRAM内容、global B、pair-high、末N128地址、坏range/identity/alias/tag拒绝。
- coordinator/实际producer admission/实际Matrix集成20项通过。实际K4096的M16/N288覆盖N160+N128尾窗、M128/N32覆盖完整128行；旧两partial到新四partial无需reset；末ACK失败及held-success abort均不发布。
- 首轮集成19项中3项在final drain遇新请求精确类型拒绝；修复薄适配分派后新增回归，20项重跑通过。失败日志保留，不计入通过。
- 另42项前缀旧门/参考/payload/chain/streaming集合通过；集合有重叠，不累加成独立测试总数。最终冷门另报。

## 全形状闭式预测（已与下文两档实测核对）

- N2048共13窗口（12×160+128），52个独立Matrix partial、39次Vector sum invocation、13个最终drain；每partial重新实际装载K1024 slab，不复用失效A lease。
- 执行FMA预测两档均1,073,741,824；有效FMA M16为134,217,728，M128为1,073,741,824。12.5%/100%只是有效/执行工作量比。
- Vector Add调用预测M16 6,144、M128 49,152，每调用16条FP32 lane。
- A DDR读预测M16 1,703,936B、M128 13,631,488B，是完整输入的13次读取；W读16,777,216B，两档相同。数值对齐的重复装A代价明确保留，不称流水优化。
- 没有seed或私有DDR partial保存；现两槽由真实Vector Add原位累积。完整硬件周期、有效MAC利用率、busy/active-lane占空比仍未知。

## M16同次真实前缀已完成

- 冻结94个执行源、13个native/固定来源记录前后未变；11个owner终态均成功。RMS至gatednorm的13份旧输出含state/scratch全部与91f批逐SHA一致。
- 新O为完整[16,2048]，32,768个BF16词逐bit等于固定官方原N2048/K4096调用及独立四K1024左折参考。此为本输入同节点观察，未给standalone O新增阈值，完整block仍open。
- 实际52个partial、39次Vector sum invocation、13个drain及52次A装载fence；O执行FMA1,073,741,824，有效134,217,728，Vector16 Add6,144次。
- 实际A读1,703,936B、B读16,777,216B、输出写/ACK65,536B，与上述预测一致。
- 整条链Matrix累计4,311,744,512次，已超过UInt32上限；实际C++/Python UInt64计数未截断。有效总量538,968,064，工作量比12.5%，不是周期利用率。
- state/history/scratch仍private，generation未推进，只有之前允许的core和stateless中间结果发布。
- M128沿同一冻结源码串行完成，见下节；未重复启动其他实际链。

## 入口错误与冷门边界

- 第一整轮冷门642项/66套通过且源前后相同。之后CLI在实际执行前发现参考报告input字段位于input_provenance.input，旧顶层读取产生KeyError；未建立实际执行summary，也未消费Matrix。
- 保留preflight失败日志，修正严格nested schema并新增1项防回退测试通过。上面M16完成记录来自修后实际执行。修后最终最新源码冷门643项/67套/195源全部通过且零skip，前后源未变；计划清单338项通过。642项只保留为先前结果。精确提交CI待收口。

输入来源说明：O owner报告中的role='synthetic'沿用未授予production数值profile的内部准入标签，不表示这两档实际case使用合成输入。实际case使用固定官方checkpoint权重和同次真实typed norm输出；与小门的合成稀疏BF16 fixture分别记录。native_acceptance仍false，逐bit观察不改完整block边界。

## M128同次真实前缀已完成

- 原进程1448秒内完成；94执行源、13个native/固定来源记录前后相同，11终态成功。
- O完整[128,2048]、262144 BF16词，逐字节等于官方原shape调用及独立四K1024左折C参考，SHA256为38b32aa2bef094242a6fc12ae6da3a15a61d9234ffde2aa5f3f41b9eca1c1cb4。
- O执行及有效MAC均1073741824；52partial、39sum、13drain、52实际A装载fence；Vector16 Add49152次。A读13631488B、B读16777216B、写/ACK524288B。
- 整条链Matrix有效与执行均4311744512，100%只是工作量比。完整硬件周期、利用率和占空比仍未知。
- 原Prep/g、chunk与gatednorm数值诊断保留；O同输入bitexact不消除前序误差，也不构成完整block通过。state/history/scratch保持private、generation不推进。
