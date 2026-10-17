# 共命名空间 class + A：仅 CHIRRTL，尚未执行

仅新增已审 ProductionQk16KernelCollection.scala（源候选 b00bf629…）。复用修复后固定 94 源、557 类及 offline_v2 兼容证据；原 strict class attempt FAIL 原样保留。无旧 emitter/classes shadow。只编此一源，预期新增精确四类：ProductionQk16KernelCollection.class 与 EmitProductionQk16KernelCollection 的 .class、$.class、$delayedInit$body.class；SourceFile 全为该源。完整 95 源、557 逐字节不变、新总561类。任何额外类均停止诊断。

容器只为同一 Chisel 命名空间：原 Bench(selected=true) 与原四 FMA 各一份，IO 全部外露/dontTouch。capacity1024/actual_job none；生产源码及刺激不改。四 FMA 是容器的真实额外兄弟实例，不计入 Bench 目标资源。检查全容器实例图无递归/未知引用且不超过20000；资源计数另从 Bench 起，核原唯一Kernel/Dense/Matrix/16SFU/8endpoint/1iDMA；五debt/4407packed与SFUabort checker原字节保持。定义总数仍768/IR48MiB，新增实际规模未知，不盲增。

A 仅核四 FMA 顶层定义和精确兄弟实例名；端口/外露未被优化的最终 SV、helper唯一命名及实际provider接口链须随后B1/B2核验。合成冷fixture只验证parser分账，不是实际生成证明。

预算沿修复后A：统一90秒绝对stop，10预检、20仅class、60emit、5cleanup共享总预算；CPU1/Java heap1GiB、IR48MiB/768定义/20000实例/输出树64MiB采样softcap/log2MiB。完整source/class/106jar/JDK/runner/compat证据前后验。原owned/strict helper字节不变。没有SV生成、链接或作业执行。

建议单次命令（需root批准）：
python -B production_qk16_kernel_collection_structure_plan_v1_20261017/run_structure.py --source-root production_silu_feedback_compile_attempt_v1_20261017/scala --base-classes production_silu_feedback_compile_attempt_v1_20261017/classes --offline production_silu_feedback_offline_v2_20261017 --cache production_qkv_protocol_dependencies_20261017/cache --java /usr/lib/jvm/java-21-openjdk-amd64/bin/java --out production_qk16_kernel_collection_structure_attempt_v1_20261017 --execute

后续B1独立授权：绑定本次新真实IR，绝不复用旧namespace IR；固定firtool共同生成SV，检查四FMA名字、端口与所有helper唯一。B2使用旧312源剔除四独立FMA、加同一新SV，共309文件，真实lint --top-module ProductionQk16KernelBench；容器不得充当验收top。

后续动态路线只拟：独立Verilator C++ harness消费上述同一SV和固定providers，重放原m1/m17刺激/独立参考、首次done即排空检查和127拍held稳定。须另行编写审核，不在本轮增加；不使用Chiseltest自动重新发射Bench而引回旧命名冲突。
