# 新 Host93 CLASS-only 有界门候选

SOURCE候选，普通/-O各13项纯mock通过；未运行Java、Scala编译器、外部包、实际组装或硬件。执行仅由父在新93实际组装/identity审通过、门源码审及资源提案获准后单次进行。已有87 JAR/HF实际获取不等于class资格。

## 来源与真实argv

固定读取已发布新Host93 SOURCE_REPLAY_PLAN、87-JAR计划、原dependency_pins与compile_only.py（仅argv来源，不加载旧92/owned_compile模块）。新93 = 原生产92+已审SiLU单表达式修复+三tap+新共同Host emitter，无Bench/Spec、无旧95身份。必须先读实际SOURCE_RECEIPT、对照固定93映射并核精确文件集合；缺真实93时在创建输出前拒绝。

JDK仅核公开java/release两个SHA，不声称完整JDK runtime树已封身份。精确93文件及87 JAR逐个边读边SHA、同缓冲复制到全新attempt/scala和dependencies，只有这份新快照进入classpath及源argv。源32MiB前置aggregate检查；JAR总512MiB且每项小于64MiB。无旧classes或热缓存合并。

java -Xmx1024m -XX:ActiveProcessorCount=1 -cp CP87 scala.tools.nsc.Main -classpath CP87 -Xplugin:固定6.7.0插件 -language:reflectiveCalls -d fresh/classes 后接排序93源。CP87按精确相对坐标排序，不加106或并集，不运行emitter。编译结束后重核新快照所有SHA和两个JDK pin，核仅新.class文件，生成class哈希账。

## 原WNOWAIT的窄投影

固定已发布run_behavior.py同raw核SHA后仅选五函数 require/save/group_state/observe_exit/bounded，四处可精确反投影：FSIZE4→48MiB、继承允许CPU集合中取1、进入原5秒cleanup撤工作alarm、log接受界64KiB→2MiB。AS namespace为4GiB，CPU120s，core0。原固定PATH/LC_ALL子进程环境不改，不继承JAVA_TOOL_OPTIONS等变量。WNOWAIT锚定、kill-before-reap及原清理规则保持；不构造新生命周期框架。

入口共享150s：预检/快照最晚20s完成；compile最多120s且绝对workstop≤140s；原cleanup最多5s，余时post/receipt≤150s。alarm拒继承阻塞或已有timer；不重启总预算。每阶段同总stop，源码/依赖漂移、超时、输出失败、清理不确认均不接受。

资源中总150、compile120、CPU1、heap1GiB、AS4GiB对应root当前授权范围；FSIZE48MiB、class树64MiB验收软界和log2MiB验收软界是需随本门确认的具体提案。FSIZE是每文件OS界；树/log界均不是OS聚合实时硬限。JVM heap不是RSS/全进程AS。不是cgroup或内核不可中断调用保证。

最终RESULT/stdout只记CLASS_EVIDENCE_PENDING_OUTER_EXIT0，terminal_success=false；save后再核同stop。父必须独立保存真实outer exit0、实际elapsed≤150、原WNOWAIT清理与新93/87/class身份审通过，才能接受CLASS。残留RESULT、SOURCE_RECEIPT或compile.json不能单独授予成功；FAILURE与非0/未知退出禁止接受。不运行emitter/IR/SV/firtool/Verilator/Host，不增加完整block0/5计数。失败保留新attempt，不自动重试或扩资源。

## SOURCE冷测/预检

    python -I -S -B test_class_gate_cold.py --repo ABSOLUTE_REPOSITORY
    python -I -S -O -B test_class_gate_cold.py --repo ABSOLUTE_REPOSITORY
    python -I -S -B run_class_gate.py --repo ABSOLUTE_REPOSITORY

冷测只核固定项目文本、投影原FakeOS及合成93/87小文件，不读取实际下载JAR或真实组装源、不执行project pyc或真实子进程。没有actual源时仍可做SOURCE预检，它不产生输出。

## 父后续唯一实际入口

    python -I -S -B run_class_gate.py --repo ABSOLUTE_REPOSITORY --assembled-source ABSOLUTE_REVIEWED_ASSEMBLY_ATTEMPT --jar-artifacts ABSOLUTE_REVIEWED_JAR_ATTEMPT/artifacts --java ABSOLUTE_PINNED_JAVA --output ABSOLUTE_FRESH_CLASS_ATTEMPT --execute-reviewed-class

上述实际输入目录、独审身份和argv必须在执行前由父绑定。执行switch只是防误触，不赋权。实际组装审尚待回报，候选不填造其收据hash或class输出。
