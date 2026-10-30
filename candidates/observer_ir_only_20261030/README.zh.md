# TEMP：原始 Chisel 观察接口的独立 IR-only 有界尝试

## 最新增补：完整 canonical / ports 观测描述符（TEMP，未 activation）

以18828f90da5a1b059a055a8c5273351a41eca946为源码基线；原155源编译与HIGH/official LOW保持。compile155后仅编译原CanonicalHighGate.scala和新ObservedHighDescriptor.scala；不调用原硬锁main、不改旧gate。IR成功后新descriptor调用原公开module/circuit/annotation semantic方法：只去Info及TargetDirAnnotation，模块及保留annotations顺序不改；实际module/annotation/class计数，不抄旧1056/8985。HIGH及annotations反序列化后须逐字节serialize roundtrip。

LOW完整端口来自原helper的low-top-ports.fir，既有artifact hash/terminal marker先核，descriptor前后及导出前再核三个输入bytes/hash。官方Parser只解析端口metadata容器，不重parse整个313MB LOW、不改变实际电路。所有name/direction/type/width均保留；85旧口逐一不变，37新增严格只读output（P0 27/689bits，MoE10/259bits），只检查122总数不足以通过。

完整canonical TSV上限256KiB，details JSON上限128KiB，另附固定provenance，三文件总上限512KiB；独立artifact白名单，仅observed-canonical.tsv、observed-details.json、provenance.json。原64KiB摘要只保留文件bytes/hash、有限计数及OBSERVED_UNREVIEWED。全部仍canonical_pass=false，不自动批准新硬件或解除后续SV/ABI/hash gate。无rawlog/IR/classes/权重/张量上传。

两个新增阶段沿已有同类helper/canonical上限：各wall300秒、RSS3GiB、heap2GiB，原supervisor与原IR 480秒/5GiB/heap4GiB及其它caps不改。全9阶段wall上限3180秒＋cleanup285=3465秒，3600秒总预算留135秒；每阶段动态至少90秒余量仍核验。旧同类耗时不是新descriptor实测，目标CI准入仍待执行。

本地[微型fixture](evidence/descriptor_fixture_20261030/SUMMARY.json)只编译2helper＋1合成driver：7.608s / RSS248766464B；三端口Parser/descriptor fixture1.763s / RSS110387200B，均native0与严格cleanup/EOF。限RSS1GiB/CPU60/wall90，MemAvailable至少7GiB（未知旧IR按5GiB保留）；未触碰旧owner。本地Debian Java不迁移CI资格，三口fixture不证明真实122口或完整数值。Python 56项normal/-O轻测另记。

本批无activation，不重用旧run；原r3路径尚未消费，保持它并要求未来source为新直接parent。下一步真实获得描述符后独立审查改变模块/annotations，建立新数值backend锁；不把观测描述符当SV生成、GCC依赖、RTL数值或利用率通过。

## 最新状态：aggregate scope r3（source-only）

原r2 run41108031789完整Scala编译通过，但IR在前置entry census被拒、未调用execute；详见[原摘要与失败归因](evidence/run41108031789/README.zh.md)。扫描仓库＋work时已计数19993加预留8超过20k即停止，不是完整总数。当前修复显式将IR条目门对齐其余阶段既有aggregate 100k；原supervisor、其他资源/cleanup门、扫描根与8项预留不变，真实准入仍待执行。

本次专用闭包618项（125813 B），SHA256 1277341d821c7ed915b15e4c500d88c6696dab23ff62a923137421b92265e0af。44项轻测normal/-O分别通过。新单次路径ci_launch/observer_fixed155_original_ir_aggregate_scope_r3_20261030_once.json仅源码接线，本包没有activation；须在源码CI后用实际source SHA另提交一次，禁止重用已消费r2。旧文字以下作为r2历史方案保留，其中616、32 tests、20k和r2路径不描述当前修复状态。新R2 122口仍未实际IR核验，数值/最终RTL各0/5。

## 历史 r2 源码方案

发布父基线为215f4670a92f29f67ba03aab52944e4653ed2aa3。专用闭包616项：原active598字节不变，加8个统一硬件观察覆盖与10个IR入口/测试/workflow；所有bytes/hash已独立核验。原32项轻量测试normal/-O均通过，不等于真实编译或发射。

仅执行原JDK/编译工具/107 JAR/固定Verilator包身份准备、完整fresh_host inventory、固定155源（8覆盖、147原文件）完整Scala compile、原DiagnoseOriginalHostMoePhaseV5空参数HIGH及official LOW。Verilator包仅供原identity inventory，不调用frontend；没有SV/native backend/权重/reference/DUT，不按模型重新elaborate，原canonical/SV门保持不变。122端口仅待测预期，不能沿旧112/119或V1 class证据。

每阶段在原supervisor.execute之前做一次只读、非原子preflight：root父子去重、lstat不跟symlink、按inode计文件bytes，保留8项元数据空间。不可读或超过原entries/tree/file/free-disk cap则不启动execute。原supervisor的memory gate、limits、monitor、cleanup全部未改；运行期仍是原采样限制，不冒连续严格上界。

独立GitHub runner与原numerical job共享hetero-exclusive-numeric-bootstrap组，cancel=false。首步monotonic总预算3600秒，阶段wall2580+cleanup225=2805秒，保留795秒。IR RSS5GiB、wall480秒、CPU420秒、tree1GiB、file384MiB、log8/raw16MiB、entries20000均不放宽。目标runner资源未预先PASS，后续有界尝试必须实际准入。

唯一上传是64KiB内的typed summary，artifact名字hetero-observer-ir-summary-实际run_id；只固定枚举/数字/hash/计数，不含rawlog/IR/class/tensor/权重或任意异常文本。即使发射成功，canonical、host全链、numerics、最终RTL及物理性能资格均为false。

本次只有源码，无activation manifest。源码发布/CI确认后才可能单独增加ci_launch/observer_fixed155_original_ir_r2_20261030_once.json；guard要求main、attempt1、单parent、source为直接parent、只新增这一文件。不得重用任何旧nonce或把旧local84990未知状态解释为结束/通过；原run41096005966的build/dedup失败证据亦保留。

完整五块M128 Chisel/最终RTL数值仍0/5。此步骤用于给新真实观察接口获取可复核IR事实，不替代完整block数值回归。
