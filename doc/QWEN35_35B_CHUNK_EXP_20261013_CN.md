# 35B Chunk 显式渐进下溢 exp 接线（2026-10-13）

## 具体功能

ChunkJob/Owner/Driver新增显式exp policy，旧默认仍调用原exp_negative及≥80归零。
新策略只接受GROUPED35B、caller-owned且已enable的DecayScalar/GateScalar、显式IEEE Vector16。
运行期资源tuple、admission、reset及终态source identity共同绑定该选择。
新策略调用已有exp_negative_ieee_rne公共操作，未修改已验证P7算法，也没有新增Scalar。
前段Scalar内部计数在chunk admission时截取baseline，终态只冻结当前owner增量；不会把前段Prep
或held-terminal重复计入chunk。统计区分abs≥80输入、旧饱和、实际subnormal及合法零输出。

该P7近似有FP32渐进下溢范围，不是正确舍入exp，也不保证Torch逐bit相同。
新opcode仍未绑定生产Chisel，Vector IEEE异常选择也仍有生产集成缺口；代码显式保留这些标记。

## 当前实际轨迹重放

使用既有M16/M128真实Prep产物，先重新核前批summary、原74源和native记录，再通过新guarded
cumsum逐项重建当前轨迹；cumsum与固定Torch实际shape/stride均逐bit一致。
然后用现有Vector Add形成remaining/pairwise差值，并调用真实ChunkOwner._exp方法。
同一个Scalar另调用旧操作作对照，参考为固定Torch2.10.0+cpu、DEFAULT、单CPU、单线程的torch.exp。
这是已保存输入的算术方法重放，未重新执行producer或完整chunk内存控制。

|规模|新exp调用|与Torch差1ULP|逐bit相同|旧误归零→新误归零|新subnormal|
|---|---:|---:|---:|---:|---:|
|M16|70688|779|69909|193→0|193|
|M128|141376|4476|136900|918→0|727|

最大绝对差均5.960464477539063e-8；1ULP是这批观测，未新增验收容差，passed和thresholds仍null。
M16有16个真实token、每head补48个零；M128有两个完整chunk64，不能把前者称128token通过。
每head/chunk调用为1个chunk_decay、64个cumulative、64个remaining、2080个下三角pairwise。
新旧对照总计各212064次公共exp请求，不把对照请求算入实际候选执行成本。
Vector Add分别95232/190464次，包含guarded cumsum及差值生成；没有Matrix或Vector Mul调用。
源码69项前后冻结；原raw输入、cumsum、输出、旧对照和官方参考均保存在ignored work并记录hash。

## 实际内存owner小门

4项测试含显式策略/资源拒绝、runtime enable漂移拒绝、读错误不发布、原操作默认不变，
以及一个32头M1、dk16/dv32合成完整chunk owner。Q/K/V为零，head0的g词为0xc2b72752，
其它head为零。70688次新exp公共请求中65个subnormal真正保留，旧饱和计数0；输出与state均为零。
同Scalar先有一笔前段请求，chunk计数正确排除它；reset保留policy并清本owner计数。
这仅证明32头缩维路径的接线/计数/状态控制，不是完整维度checkpoint数值验收。

实际M1小门：读70309888B，写5310464B，2363137个软件transport ticks，scratch/output/state均未发布。
Vector Add/Mul issue为1025024/944128；Mul→Add主机batch914432次×16lane，
即14630912个分别舍入的执行对，不是FMA；semantic有效Vector MAC尚无合同，不报伪利用率。
Scalar内部节点计数独立披露，不能再当公共Scalar请求或硬件周期加总。

## 资源与未关闭项

使用原Vector16和同一Scalar，没有新增算术阵列或DDR布局。软件ticks没有计入真实Scalar/Vector
算术延迟，不能拿不变ticks宣称流水/利用率无代价。完整硬件周期、占空比、80%/90%目标仍未知。
原generator跨yield局部list和完整活跃寄存器上界仍未证明。

下一步是同一次真实RMS→QKV→Conv及A/B→Prep尾部接完整32头chunk；要沿用实际memory、Scalar、
Vector和已ACK的Prep region，不导入raw冒充producer。ChunkResult为staging终态，不能套前缀
要求output.published的helper；history/state最终仍需完整block joint fence。
完整维度M16/M128事务预算已证明超过旧20M watchdog，需采用独立有界预算及wall deadline，
保留超时pending义务、state/scratch覆盖证据。M16先行，之后才运行真实M128。
Prep g4ULP、standalone chunk未分配门、MoE完整链和RTL验收仍open，原已分配数值门不变。

最终冷门547项、52套、158源零skip且前后不变；计划清单91项通过。机器摘要的小owner
结果绑定最终冷门4项日志；实际轨迹原raw与69源冻结证据独立保留。
