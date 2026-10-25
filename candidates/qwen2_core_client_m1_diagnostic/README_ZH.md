# DIAGNOSTIC FAIL_CPU150：两个真实主线程采样点

**ACTUAL_DIAGNOSTIC_CPU_FAIL_AUDITED_WITH_TWO_THREAD_SAMPLES / FAIL_DIAGNOSTIC_RETAINED。** 新150CPU诊断失败保留，不是M1行为、数值、SV/RTL、full29或MAC利用率PASS；原600CPU FAIL与compile/selected-on CHIRRTL/完整128软件观测域结果不变。本包没有新NoCSE候选、编译、运行或GO。

## 已发生的结果

一次原normal_m1 JVM诊断：root returncode 1、outer timeout=false、wall **150.59583115798887 s**。CPU门在采样 **150.00205305999998 s** 超限，最终aggregate CPU **150.46189109 s**。正常exit字段仍null；cleanup直属leader reap=-9且独审闭环。这些字段不可混为一个退出码。sampled RSS高水位 **1,211,338,752 B**，不是连续全树峰值或heap OOM/GC根因证明。

没有READY、OBS、CASE_PASS或ScalaTest成功完成；真实clock总数未知。诊断reader可以在失败后分类已有文本，但**其结果不清除CPU/进程FAIL，也不调用行为验收门**。新公开源码里的任何成功字样都是门定义/合成fixture，不是实际行为结论。

独立实际审查分层：11,155身份条件、99 dump条件、1,248 runtime pins、4 inventories、20 staged classes、24原artifact / 59,680,922 B、30个stat端点检查。两个完整形态的线程文本块，各13个thread records、JNI terminator和heap summary；这不等于完整JVM dump语法验证。LOW IR58,897,360 B，SHA256 `71a27f80112970011761ffe361e6466a57a53f4eae95a816a252bc162ec4ea56`，与旧600CPU失败文件字节相同；仅opaque hash，未全量解析/验证IR。

## 两个点真正说明了什么

- 约60 s：实际ScalaTest主线程位于 **Treadle PrepareAst → FIRRTL InferResets**，递归遍历statement。
- 约120 s：同一主测试线程已推进至 **PrepareAst → CommonSubexpressionElimination → MemoizedHash / HashMap lookup**，递归计算Mux/SubField/Reference/BundleType/Field/UIntType结构hash。

[`SANITIZED_MAIN_STACK_SUMMARY.json`](evidence/SANITIZED_MAIN_STACK_SUMMARY.json) 只保留独审去地址栈中相关Java帧的有序子集；没有native地址、PID、锁地址、原始thread header或私有绝对路径，省略hidden-address和无关帧。不把有选择的摘要称为完整原栈。

结合固定官方源码调用顺序，这两个栈位于 `TreadleSimulator.createContext` 内，所以**在这两个采样点之前，初始 `Compiler.toLowFirrtl` 已返回**。这是actual frames＋源码顺序的推论，不是仅看`.lo.fir`扩展名。后续PrepareAst又以currentState=Nil安排LowFormOptimized/内存时序转换；CSE lookup构造MemoizedHash wrapper，lazy hash只属于该wrapper，不是全局按表达式身份永久缓存。

**两张栈不是全程profile。** 不能说这些函数占全部150秒、是唯一瓶颈、解释旧600秒失败，或证明120秒后未进入graph/reset。两点不是测试刺激/Matrix脚本/首reset位置，但不能据此声称全程零clock。没有节点访问频次、hash冲突率、渐进复杂度或逐阶段CPU实测。原collector累计main CPU29.53382→69.155秒（差39.62118）也不是CSE的CPU占比；VM Thread累计差不能标成GC CPU/pause，JIT线程累计也不能全归给其显示的当前方法。采样信号本身可能扰动被测过程。

## 信号安全证据的准确层级

两个receipt slot记录目标work60/120 s，实际send work **60.01703250099672 / 120.00894445297308 s**，API正常返回成功及handler-caught bit。已审固定源门限定本次新Popen直属leader，pidfd绑定、存活/未reap、身份/cmdline/exe/handler与资源重检，无任意数字PID降级或进程组诊断信号；旧cleanup helper不改。

**保存的是共享diagnostic anchor、slot返回元数据和实际dump；没有每次发送当时完整的原始/proc identity/cmdline/exe/pidfd快照或syscall trace。** 因而不能宣称独审逐次重放了系统调用/全部身份检查，两个dump也不是形式化的一一发送确认。source资格＋anchor/receipt＋两个文本块相互支持，不消除所有TOCTOU/信号延迟合并/输出截断风险。没有向旧退出PID补发、没有第三次请求或自动重启。

## 源、历史与范围

公开 `check_diagnostic.py`、`test_diagnostic_checker.py`、`DIAGNOSTIC_EXPECTATION.json` 均为原字节；可运行 `python -B test_diagnostic_checker.py` 与 `python -B -O test_diagnostic_checker.py`，仅小合成文本。reader本身**不是自动脱敏器**，它返回的真实thread header可能包含私有地址；不得把任意真实输出直接发布。本包摘要是另行严格选择并复审的安全投影。

1734旧诊断候选仍STOP、从未执行：已观察low-file snapshot异常原来只作sampling skip，可能绕过输出资格FAIL；r2把该异常纳入guard→cleanup/FAIL传播。不扩大信号目标/次数，不改20类、Scala/Java argv或资源。历史source review的318合成控制、11,314身份检查、58固定JDK检查与后来实际审查分开，不能相加当硬件测试。原4条W005仍保留。

原4Scala/20新类/550baseline类/106官方JAR身份及原600FAIL使用既有公开引用，不重复大清单。新增官方sources.jar仅作为只读分析证据：firrtl2/chiseltest 6.0.0 Maven URL、SHA1/SHA256、抽取source hash及3个runtime class witness；**不加入实际classpath，不发布JAR/class，不声称已重新编译证明完整source-to-binary等价**。本次未改core/PackedClient/数学/刺激/阈值/clock界限。Matrix与Memory仍为原脚本端点，不是实Matrix FMA或完整数值验收。

实际独立限额1CPU、CPU150/work180/cleanup190/total210/outer240 s；heap1GiB、stack4MiB、AS4GiB、采样RSS2GiB、log2MiB、输出树采样256MiB、单文件192MiB不变。child硬限与aggregate采样门不同，不是cgroup/全系统隔离，sample gap最大0.05552178097423166 s。原隐式classpath槽只在pre/post/review端点确认缺失，不冒充持续classloader隔离。

## 下一步仅是计划

官方 `NoCommonSubexpressionEliminationAnnotation` 可作为关闭可选CSE的候选方向；本包只记录其存在，**未纳入任何未执行新Spec/配置/类，也没有关闭、测量或采纳优化**。跳过CSE可能扩大后续graph/每clock开销，没有完成或加速保证。旧LOW文本不是完成PrepareAst后的透明缓存，不能据扩展名跳过检查；任何后继变更或运行都需新精确审查/授权。
