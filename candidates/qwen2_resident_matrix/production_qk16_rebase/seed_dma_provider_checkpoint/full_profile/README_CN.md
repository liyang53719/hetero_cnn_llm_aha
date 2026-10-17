# 固定完整 Bench 低内存工具 profile，待独审及 root 单次授权

相对 noinline 实际超时失败，合并两项已独审源码候选：唯一 front_control provider 在 BEGIN 候选上追加 beat/commit 两个 READY 的 retained-quiescence（零状态/端口/算术变化）；原6 hints原样保留，追加内部 idma_axi_read.read_req_o/read_rsp_i 两精确 split。每个hint都在全部307源中检查模块和指定字段唯一，不以局部file检查代替。

先前6069…组件PASS只覆盖BEGIN版本；本次reserved-ready版本仅SOURCE GO，不冒用组件通过。两态65536组合与真实源码互斥证明不等动态FSM或X/Z证明。共307源、固定共同SV、完整4096配置，唯一provider路径/hash变化，其余原输入不改。

工具profile明确同时保留-fno-inline并新增-fno-dfg。固定官方HTML1022–1049指出后者是关闭pre/post两个DFG优化的别名；固定Verilator_v5.032.cpp283–308：两个DFG都关闭时extract也跳过，fInline独立控制inlineAll/linkDotArrayed。313起const/dead、327起实例化/层级scope等仍运行，没有跳过子树/黑盒化/缩阵列。输入电路语义不改，工具优化路径改变。可能减少DFG中间图内存和耗时，也可能增大后续表达式/模型，因此不保证更快/更省或完成；合并多项变化不能归因单项性能改善。

预算保持210s总/180s工具/10s cleanup，CPU1/AS6GiB/file16MiB/log2MiB/tree64MiB软限。初始和spawn前MemAvailable≥8GiB双快照并记录值，非预留；root协调无重并行。21精准WIDTH规则保持，其它warnings fatal。上次180满CPU仅证明预算耗尽，未有pass进度；原FAIL不修改。

诊断选项只读审查：官方--debugi-srcfile提供按源文件级别日志，但单独Verilator.cpp现有UINFO只有启动/收尾，不能提供逐phase进度；--debug会连带dump，--stats在正常结束写统计，超时不保证可得。此候选不加未定量日志选项或大dump，保持原leader CPU/HWM有界采样。

冷测试：python -B test_cold.py 与 python -B -O test_cold.py。仅在独审和root一次GO后：python -B production_seed_dma_noinline_nodfg_plan_v2_20261017/run_lint.py --workspace /workspace/scratch/f28987e955ed --out production_seed_dma_noinline_nodfg_attempt_v1_20261017 --execute

仅lint，不native build/sim，不完整Host或M128数值/PASS。失败保留原诊断，不自动重试/增加AS时限/waiver。
