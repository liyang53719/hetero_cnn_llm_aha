# 真实 Matrix 路线：两新增 Scala 源实际 compile-only PASS

**PASS_ACTUAL_TWO_SOURCE_SCALA_COMPILE_ONLY**：root单次真实 Scala/JVM 编译 exit0；两新源得到3个class、63834 B，独审18390检查、1325 pins与5 inventories通过。**只关闭编译/静态容器身份门，未进行 Chisel elaboration、provider运行、数值或MAC验收。** 本包不纳后继 ChiselMain/emitter 候选。

## 源码接线意图，不冒充运行结果

原字节 `OrderedQkRealMatrixCore.scala`（3837 B）＋`OrderedQkRealMatrixCollection.scala`（1530 B）公开。前者实例化原 OrderedQkBehaviorCore(true)、MatrixPipelineService 和 LegacyMatrixStreamClient；packed lease 选择来自原Core，drain来自真实service状态，PV走原legacy接口。9 forward/4 reverse选择与payload广播，不用脚本tile/PV回复或 steps==8 drain替身。**这只是已审核源码及已编译引用，不证明接线已通过Chisel构造、运行或FMA数值正确。**

原8×512 Matrix端点与数学资源保持，不改成更小计算体。Collection的四个FMA兄弟根用来共享未来发射命名空间/ABI定义，不是selected shell内部另加4条计算路径；本次未实例化/发射，不能从class constant-pool推断实例数、reset或生成后的HardFloat ABI已闭合。PackedClient与原Matrix/Legacy依赖未改。

Attention kind `assert`不是通用生产Host拒绝门；测试必须约束合法Attention job。foreign/missing memory/done身份 fail-closed，不保证任意乱序/环境不回复时无条件恢复。`issuedSliceSteps`及继承`executedMacs=issued delta×512`只表示issue bookkeeping，**不是completed/useful MAC**。

## 实际编译与 class 身份

- Collection.class：14225 B；Core匿名Bundle：7508 B；Core.class：42101 B。Java major52/minor0，SourceFile对应两源，无新增main。
- 审核完整class容器、CP引用、Code边界/长度、内名及hash；**不是JVM字节码语义验证/模块构造**。本包仅简短类名/计数/hash与选定CP类型引用，不上传class或方法字节码。
- 原550 baseline class＋来自既有20输出中精确14个Core/Qwen2Block override（替换10、新增4）=**554 stage /9631197 B**，全套实际hash与0444模式不变。排除既有新增Spec/Elaborate各3类作为override；新3类单独在newclasses，并未放回本次stage。未来557 unique只是可构成的身份集合，**不是已elaborate/执行557类**。
- 106个官方依赖JAR沿用既有hash/URL及排序，显式Chisel插件，保留Java21/Scala2.13.16与源输入顺序。旧92源recipe里只有60直接公开blob，其余32为recipe/external输入（含20 HardFloat外部源）；**本小包不冒充完整runtime可脱离这些前提重建**。
- 560实际文件 /9773450 B =554 staged+3新class+CLAIM/RECEIPT/log，全部只保留必要hash引用，compiler.log与root stderr为0 B，不据此宣称所有warning启用或硬件正确。

## 13 provider 与 ABI 仍是 source-qualified

原历史定位中缺失的13份provider已由源独审核验精确hash恢复定位，20声明module；**仅只读定位，不是已stage/编译provider的RTL闭包**。不上传provider SV，也未把它们作为本次Scala输入。

保留22个未seed endpoint端口子集、4个ICG端口、4 FMA源声明ABI与23个额外端口清单。未启用seed/transposed-dense；生成后的namespace/宽度/reset/多余端口处理仍需新门。旧seed1局部PASS、旧完整4096在4/6 GiB的lint资源FAIL不迁移或抹除。

## runtime、预算与清理

1323 manifest项＋manifest/supervisor=1325 pins；5 inventories。root前/后56已知parent端点、12 absence及C.UTF-8三元组一致；角色/hash投影不是系统pyc/JAR/JVM字节公开，不是持续全宿主机隔离或所有动态加载跟踪，也不回填旧cache覆盖缺口。

CPU **10.378072406 s**，inner **10.406169352005236 s**，outer **10.503095433989074 s**，采样RSS **254390272 B**；最大采样间隔0.06563258997630328 s，非连续峰值。固定1 CPU，CPU/work120 s，cleanup145 s、total150 s、outer180 s；2 GiB sampled RSS/4 GiB AS、64 MiB tree、48 MiB单文件。一次执行无重试/加时。

保存cleanup两次完整pre-reap扫描仅Z态leader，无nonleader，再reap、exit0；helper中一次pre-reap containment SIGKILL记录**不等于编译异常退出**。独审只核保存证明，没有重建live handle/重发信号，不扩大为whole-host逃逸后代证明。子进程 CORE0仍不能保证系统piped core handler不启动。

## 小源控制与复现

原literal checker原字节发布；原10项tests只把一个私有绝对路径转换为已pin公开Qwen2Block。`SOURCE_PINS.json`保留原/转换后hash及唯一字面量变换身份，所有断言不变。新helper只复制小源码、从550＋14旧hash重建554项**元数据**，不读取或产生class，不调用Scala/JVM/native：

```
python3 -B candidates/qwen2_core_real_matrix_compile/prepare_source_controls.py --repo-root . --output NEW_SOURCE_CONTROL_DIR
python3 -B NEW_SOURCE_CONTROL_DIR/test_source_contract.py
python3 -B -O NEW_SOURCE_CONTROL_DIR/test_source_contract.py
```

合成literal/boolean PASS不是Chisel type/行为证明。`COMPILE_EXECUTION_ROLES.json`保留实际两源编译参数的角色模板；106 classpath可按既有官方pin恢复，554类必须按原recipe/build证据重新产生并验证。该模板**不自动启动任何后继阶段**。source审里的旧“尚未编译”及G1未来门为历史记录，后来的本次compile收据单独闭环。

仍缺：实际collection elaboration/完整provider生成闭包、全tile只读probe、冻结非零独立逐步FMA参考、真实内存ACK/backpressure/结果drain数值对照、full128/full29/fullblock与90%MAC。M1/M2/M3/M17脚本端点有限PASS及所有旧FAIL/STOP保持，canonical整体任务不置done。
