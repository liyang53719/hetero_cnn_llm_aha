# 原始 Public PV16 M128 paired-reference linked launch

## 中文计划
- 已完成：独立 native16/128 数值通过及精确 AVX512-BF16 dispatch 实例证据；runtime 接线冷测试通过。
- 已完成：最终 linked SETUP+ASSETS admission、十二个严格生成源码身份及73项冷测试 normal/-O（8.183/8.767秒）。实际 source-only composition 校验283个源码身份，禁止数值包和 native 加载。
- 进行中：独立审查及真实本地 Git clone/compose 身份检查。
- 待完成：审查后的原始 Public M128 实际运行。没有继承历史全链路 PASS。

本层保留原始 Public owners/Matrix/Host 和两个 C++ hardware references。新增两个 overlay 只把 producer/admission 的 runtime import 绑定到最终 source contract；原有三个控制入口也只改身份导入和安全 backend diagnostic dispatch。所有算术、原始数值阈值及 gate 不变。

一份 fresh setup 同时绑定双 recipe ELF/receipt、generated gate、native16→128 prerequisite、全部原始 exports 和严格完整九条 avx512_core_bf16 BF16 matmul；观察到 AMX 或未知 dispatch 会在 Public 计算前失败。CPU flags 不能替代实际 primitive 资格。

工作预算：900秒 setup、2400秒内部 Public、2430秒外部数值阶段、3420秒绝对总期限；整个 job 60分钟。仅 workflow 自身路径 push 或 manual 触发，run_attempt=1。最多两个顺序 VM placements：只有第一个在 clone/setup 前经严格校验的 CPU_UNSUITABLE 才能启用第二个；最多一个 setup/Public 数值尝试，其它失败立即终止。第二个仍不合格则整个 workflow 失败。输出只允许三个固定安全 JSON，权重、数组、完整私有日志不上传。

当前为准备代码，尚未运行 setup/native/Public。

## CPU placement 修正
实际 run38949728447 在 environment backend gate 拒绝，耗时49.381202秒，cpu_avx512=false，未进入 Public。修正仅加入下载前的必要硬件资格筛选：所有 processor 记录都须有原 AVX512 flags 与 avx512_bf16；任一 processor 出现 amx_tile/amx_bf16/amx_int8 时保守视为本 profile 的 placement 不合格。它不是 Torch dispatch 或数值等价证明，不设置任何 ISA override。缺失/损坏 cpuinfo、override、超时、source/Git 错误均不是可换 VM 的 CPU_UNSUITABLE。

后续仍必须通过原 Torch backend gate 和 fresh native16/128 各九条实际 avx512_core_bf16 dispatch。packages/编译/native/Public 失败均不重试。早期拒绝也保留固定 summary/progress/source_hashes；所有 started 标志必须为 false 才能换 placement。当前变更仅冷测试，未执行新的 setup/Public。

CPU placement 修正冷测试：runner49项 normal/-O通过；linked完整82项 normal/-O通过（8.058/8.290秒）。包含混合processor、AMX union、malformed/late资格失败、精确source/Git/receipt负例及setup/native失败不换VM。
