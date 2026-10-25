# normal_m1 实际 CPU600 FAIL：保留失败与只读阶段诊断

**CONFIRMED_ACTUAL_NORMAL_M1_CPU_BUDGET_FAIL / FAIL_NORMAL_M1_TREADLE_RETAINED。** 本片不是行为、数值、SV/RTL、full29 或硬件利用率通过。旧四源编译、selected-on CHIRRTL结构PASS及完整 M128 软件观测域/packet证据保持，不被本次失败否定；旧 FAIL/TEMP/STOP 和 canonical 状态不改。

## 一次实际尝试的终态

原 root returncode **1**、outer timeout=false、wall **600.6606750690262 s**。JVM worker 已启动，监督器在 sampled aggregate CPU **600.0102720120001 s** 超过独立600秒门后清理；最终 aggregate CPU **600.437616799 s**。原正常退出字段 `exit_code=null`，cleanup 的直属 leader reap code **-9**；这是不同字段/阶段，**不得用 -9 覆盖原 null**。清理独审闭环只针对受锚定原进程组及已观察身份，不是任意逃逸进程/全局隔离证明。

日志2329 B保留7个 class origin、4条W005及ScalaTest开始信息；**READY=0、OBS=0、CASE_PASS=0**，无ScalaTest成功摘要。实际行为结果 checker **未调用**，因为已有资源错误且没有合格正常退出。新 checker 源码存在或合成测试通过，不能变成本次真实checker PASS。

独审分层：9,484条身份核对、72条语义条件，1,191 runtime pins（1,189准备pins＋manifest/self 2项）、4 inventories、20 staged classes、24原始 artifacts / 59,625,551 B保持。两处隐式 manifest sibling JAR slot 在准入/后检/独审时均不存在；这不是连续 classloader/global-process confinement。计数是身份/语义条件，不是硬件数值测试数。更早 source review 的328个合成控制属于准备期，不是本次行为实测。

LOW IR文件58,897,360 B，SHA256 `71a27f80112970011761ffe361e6466a57a53f4eae95a816a252bc162ec4ea56`，由身份独审一次完整opaque hash绑定；语义独审只读有界头尾，**无全量IR解析/合法性证明**。没有将这个大产物、JAR、class、输入/权重或raw日志上传。

## 可以定位到哪里，不能定位到哪里

只读 author 诊断认为：最终LOW文件mtime相对claim mtime晚 **46.39577955 s**；结合root wall估算，约 **554.2648955190261 s** 位于该mtime之后仍无READY。**这只是文件系统时间线推断，不是单调时钟阶段计时或CPU分摊**；claim写盘晚于监督起点，也没有时钟跳变排除证据。文件已出现并有合理头尾，不证明 `toLowFirrtl` 返回、lowering完成、全IR有效或实际热点函数。

固定源码的 framework 自动 reset1 在用户body首行 READY 之前。因此没有READY也**不能推出零clock**；真实解释clock数、阶段时间、具体卡住函数均 UNKNOWN。后续 FIRRTL transform、PrepareAst、SymbolTable/DataStore/ExpressionCompiler/Scheduler、端口映射、首次组合求值/reset、GC/JIT只是未测假说，不是已定位根因。RSS采样高水位 **1,244,446,720 B** 不是连续峰值，不能据此判定heap OOM/GC thrash；也无死锁或进度证明。脚本Matrix poke/FMA不能被指定为本次已观察根因。

诊断报告的未执行150秒采样方案/信号设计/新loader、native替代能力检查均**不纳入本包**，也没有新增claim/GO/运行或预算。任何后继执行必须另审；本片不自动重试原600秒用例。

## 精确源与模型限制

`check_behavior.py` 和 `test_behavior_checker.py` 是原字节std-lib源码，不是模拟器/完整FIRRTL validator/数学oracle。它要求调用方先验证正常exit0、cleanup、源/类/JAR/argv身份，再检查日志、单用例终态与有界LOW声明；成功语法常量不代表发生过成功。

`BEHAVIOR_EXPECTATION.json` 仅将7个class-origin中的机器路径换为新临时目录下的合成角色：六项改变、一项newclasses占位保持；其余字段完全不变。**这是合成用例模板，不是原真实expectation/config，也不是运行授权。** 所有原件hash及改动字段单独列出。可在本目录运行 `python -B test_behavior_checker.py` 及 `python -B -O test_behavior_checker.py`，各35个小合成用例；不会启动JVM、读取真实IR或调用真实M1结果门。

4 Scala原源、92-source baseline recipe、550旧类/20新类和106官方JAR pins全部引用前一已发布包，不重复大manifest。13份官方backend源码URL/Git blob/SHA与6项binary metadata pin仅表达固定源码/类来源；constant-pool不是完整调用图，不能把可选后端条目存在当实际加载/执行。

原 DUT 测试仍为独立探针副本（不是原核心同字节），原 PackedClient 不改。Memory/Matrix 是零/合成脚本端点；没有真实Matrix FMA、DDR全地址、完整tile复算、Host/full21/full128 RTL闭环。预期M1计数owner1、QK12组/96steps、PV96、memory384、输出6144 B均只是**未达到的成功门**；accounting512Steps864为合成接口账目，不是实测MAC/周期/利用率。4 W005保留，静态256组合范围分析不是Chisel行为验证。

## 监督器与资源边界

私有监督器只给原hash和角色化变化/参数投影，不公开硬编码运行路径，也不伪装成完整可直接启动的portable supervisor。此次独立配置为1CPU、CPU600、work720/cleanup730/total750/outer780 s；heap1GiB、stack4MiB、AS4GiB、采样RSS2GiB、log2MiB、输出树采样256MiB、单文件192MiB。它不是沿用原结构120秒或更早60秒提案。child CPU/AS/单文件硬限制与aggregate CPU/RSS/树的采样门分开，不是cgroup或全盘配额；sample间隔最大0.05539007700281218 s。实际只触发CPU门，不能推断其他限制已达峰或新预算必能成功。
