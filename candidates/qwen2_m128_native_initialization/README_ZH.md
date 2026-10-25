# Committed-source 见证及首 PC 前真实初始化

本包发布默认关闭的两文件source witness修复、真实initialization-only分支源码和一次有限实际执行证据。唯一native_init01通过真实构造链、reset、Matrix guard及5个固定Scalar FP32环境探针，正常进入host decode pc0/events{0}后，在execute_public_prefix首PC前停止；Rope monitor正常enter/exit及两检查点均通过。不能称“无native／无浮点运算”，也不是完整DUT数值或完整21PC验收。

## 两次旧失败与见证修复

两次旧真实DUT失败原件、claim和源不改。第一次是metadata TemporaryDirectory清理的fd-relative open被封闭oracle门拒绝，已由独立持久metadata后像及metadata-only实际冷验处理。第二次初始化到ScalarService的source_identity时，原recipe Git subprocess不适用于已组装source副本且被策略拒绝。不能放开全部Git、伪造.git/HEAD、改旧pins或把有限初始化成功追认为旧DUT PASS。

见证补丁仅给ScalarService→source_identity→extract_sources加两个默认None的keyword。默认路径仍走原Git；显式opt-in核固定manifest原始hash、commit/tree/blob/SHA/size/schema/types/fields，核真实C++原字节、Git blob SHA1和工作C++一致，继续原三个section、七份Scala与ALU整文件guard及helper/math原文。所有数值函数保持原式。不提供一个参数就失败，失败不回退；witness模式git_head=null，公开来源commit/tree/blob单列，不伪造本地HEAD。

见证C++是既有公开源码，不是权重：23995 bytes，SHA d757e1271210e260ca320cddf4175c306d3cf52835ea45f20ca9dfb56ac34db5，blob e40538df77611f10e39e70d5520397886a5607c8，来源commit 9a639053f797b19fba5b6d9cfe830dc8c3009730、tree 78752201929029bc6b084d5e89ae82ec8c7e1575。witness/IDENTITY.json固定699 bytes、SHA0652c9a94fc1e3498ed925e0f73116634a2c2f73fcc81eb7dc2211fdd5305286。

## 实际初始化范围

沿原正常loader/guards、真实CDLL和ABI配置、14provider逐hash不可变bytes、public21 fixture及metadata、PhysicalMemory/FullGraphMemory、DenseReductionOwner、td_reset/sf_reset_bf16_v1、ProfiledMatrixService、ScalarService、前端/HostControl/owners/ReducedPublicExecution、ObservedSiluLibrary、RopeOperandCapture真实构造与进入。允许原必要FE_TONEAREST、FTZ/DAZ检查、清81920B accumulator与原native状态、guard enable、地址/大小查询及5个signed-zero/subnormal FP32探针；公开证据省略实际地址。配置symbol仅dlsym/argtypes，不称已经执行其task kernel。

真实host初态是decode、pc0、program21、events{0}，不是全idle。两检查点核原共享对象、空债务、零task计数及未调用provider读函数，monitor只有预期started→closed/cleanup变化；正常退出不额外reset/abort覆盖证据。不进入首PC、host/owner tick、readcmd/descriptor transport、job/group/step/seed/retire、scalar.op、SiLU vector或oracle读取。比较器只构造无读文件closure，未调用。零计数结合fresh进程、source-bound停点、原hook与实际状态才构成有限证据，不是假称通用syscall拦截或独立每native符号计数。

实际205 cache events关联203源，NORMAL200/NATIVE5，所有cache bytes仍拒绝，named-local compile/marshal摘要独立复证；不能从exec audit推断模块体完成或泛称marshal跨进程稳定。345最终modules和20映射文件完成资格检查，原namespace/Cython raw FAIL保留后只对已知重复/两扩展关联作精确qualification，不能说raw全PASS。

## 实际资源与资格

1 CPU，20 CPU秒每进程硬限含线程，25wall监测＋cleanup3秒，1GiB AS硬限，512MiB树RSS采样限非hardcap。实际worker9.634212359秒、reaped CPU9.571733秒、sampled RSS195698688 bytes；70产物共6595226 bytes含receipt/seal，低于32MiB；2091 pins、367冻结文件、3760独审checks通过，worker已reap且无剩余自有进程。原receipt、seal、worker、独审hash与公开projection各自身份分开。

通过仅PASS_PRE_FIRST_PC_INITIALIZATION_ONLY。first_pc_entered=false、workload_numerical_execution=false、observed_domain/full29/event_protocol/actual_terminal/hardware均false。后续完整DUT必须新profile、exactreview和一次GO，不复用已消费账本。四非物化节点/三个因果域、原数值阈值保持；实际RoPE provider容量1024、canonical/active128、其余零、double math.pow/cos/sin后FP32，256仅旧参考诊断标签，官方32768不改。固定4096 MAC和legacy PV63.57%上界仍挡80/90%，不作RTL/时序/性能宣称。

## 公开复现范围

witness_postimage两源码、candidate_postimage/runner.py和init_gate_source源码均原字节。两份patch只适用于pins的精确preimage，不可套裸main假定兼容。INIT runner patch是本包从两个固定后像直接生成的源码差异，不是额外执行证据。witness20×2和init95×2原日志仅记录历史有界stdlib synthetic测试；路径依赖的admission/test文件不公开其私有安装位置，仅保留hash，不声称这些历史测试可直接公开checkout重跑。

本次打包没有target import、probe、cold或任何目标测试重跑，没有创造未经实际执行的新public adapter。完整replay需 supplied exact源码/解释器/依赖/ELF/provider/oracle及历史FAIL闭包、真实sourcebindings和新本地config/exactreview/单次技术GO；公开文件不是自包含payload/runtime。私有full config、APPROVAL/claim、raw modules/maps/worker、PID/object id、physical allocation/provider/native地址、权重和tensor均不上传。raw state整体不复制，只给原hash和经过筛选的零计数/booleans，地址相等性由原独审支持。
