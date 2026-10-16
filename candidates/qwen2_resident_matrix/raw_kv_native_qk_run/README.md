# Fresh native QKV + QK 候选验证

## 中文计划
- 已完成：QKV-only fresh native16 PASS；native128 只剩 scores/logits 失败，其上游 QKV/q/k/cache/repeat bit-exact。
- 已完成：QK 候选19项冷测试与真实 C++ 微型合成检查；随后真实 combined native16 PASS、native128 仍失败。run38934796546 的 qr/kr 已出现差异，不能将变化孤立归因于 QK；完整安全证据见 raw_kv_native_qk_results。
- 已完成：v2 诊断实现及冷控制测试；记录每模式 oneDNN primitive、CPU feature、原始输入/各阶段双方哈希与双库 fenv，只修改观察，不修改算术。
- 已完成：100项完整冷测试 normal/-O（21.444/20.889秒），252-source/221-setup/10-overlay 真实 Git clone/compose/re-exec 来源证明；全过程阻止 numerical imports、CDLL 和 producer 执行。
- 进行中：最终独立审查与发布准备。
- 待执行：审查后一次有界 fresh native16→native128 诊断。当前没有 v2 实际运行结果；Public/full-block 仍未进入。

## v2 诊断边界

v2 使用新的明确 source contract，252 个来源（含 contract）、原始221-source setup、10个原有 overlays。冻结的 QKV/QK recipe 文件和原始数值判据保持原字节。额外的零模糊 patch 只给生成 gate 增加严格类型的可选诊断参数，在既有 native_forward 调用周围使用 PyTorch2.10 官方 `mkldnn.verbose(VERBOSE_ON)` 上下文；AST 逆投影检查恢复整个原模块。该 API 只控制日志，不设置 ISA、backend 算术模式或线程选项。

每个 BF16/FP32 调用的 C stdout 经独立 pipe 排空；私有日志最多2MiB，不上传。仅投影固定 primitive/implementation/ISA/layout/dtype/shape-role 枚举和有界顺序计数。未知或截断证据明确标记不完整。完整捕获但没有 oneDNN execution 的 FP32 scope 只标记 NO_ONEDNN_EXECUTION_OBSERVED，不推断其实际 backend；只有原始全部 gate/导出/source postflight 完成时，才可作为已完成的观察。BF16 仍要求实际识别到 execution。M128 的方形 attention primitive 仅标记 ATTENTION_SQUARE，不猜测 QK/PV。CPU 扩展 flags 是观测，不替代原 Torch backend gate。

原始 RESULT 已有每阶段 actual/reference f32 SHA；验证后投影两模式全部29阶段哈希。13个固定输入 tensor 的 canonical digest map 与可变 HTTP receipt metadata 分开。两库加载前后和 Recipe/gate 前后只读取 x87/SSE rounding、FTZ/DAZ；不调用 setter。额外 host 诊断存储不是硬件 SRAM。所有 safe 字段有固定 schema/数量/类型限制，原始 stdout、CPU model、路径、张量、weights 均不上传。

诊断数值结果与观察完整性分别记录；任何数值失败保持 FAILED，诊断证据不能替代原始29阶段结果或提升 acceptance。库/build/source 哈希、最终 source postflight 与完整诊断同时满足才允许本 profile 终态 PASS。

## 数值与来源边界

本 profile 组合两个独立、分别验证的库。旧 QKV recipe 保持已发布字节；新 QK 库只计算独立路径自己的原始 K128 dot，原始 BF16(dot)、除以 sqrt(128)、BF16(score) 保持不变。所有官方前向、softmax/PV/MLP、原始29阶段记录/28个 BF16分配判据、两种模式各9项语义和阈值均不修改。新生成脚本保持在私有 checkout 外，精确 SHA 固定。

M16 和 M128 使用同一 combined Recipe identity、两库/source/pins；原始 small_gate 必须验证本次真实 M16 RESULT。QKV-only 的旧 PASS 不能作为新 M128 prerequisite。安全阶段报告既保留 QK 库身份，也单独记录 QKV 库/receipt/pins 哈希；`backend_order_proven=false` 明示候选身份，不把有限实例结果宣称为通用 backend 等价。

原始221-source setup context 只服务未修改的 preflight/environment/acquisition。新 union contract 覆盖全部执行来源、两个 recipe、两份微型证据、本运行层及独立 workflow；每个子进程前后和最终收据前检查完整来源。十个原有 setup overlays 不变。源码只从当前事件 Git commit 本地 clone，不网络 fetch；原始 checkout 不覆盖。

## 预算和 placement

每个 placement 的绝对900秒从 clone/preflight前计时，跨 re-exec 不刷新。固定阶段上限 preflight20、environment120、acquisition420、kernel30、native16 60、native128 120秒；均受总剩余时间限制，保留5秒清理和1秒收据。两个 C++ build 串行，共享原来的30秒 kernel deadline；各自 sole-owner 清理 compiler 进程组，不产生嵌套 supervisor 竞争。原始 native 算术和包版本不变。

保留最多两个串行标准 ubuntu-24.04 placement。第二个只在第一个来源绑定的 package前 CPU_UNSUITABLE 收据被验证后启动；解析/来源/安装/backend/编译/数值失败均停止，不进行数值重试。必要 CPU flags 不是 backend 证明，原始 Torch/MKLDNN 严格 gate 继续执行，不设置 ATEN override。两次 CPU不合格必须整体失败。

工作流仅自身路径 push/main 或 manual，run_attempt1，单 job20分钟/执行16分钟，冷测试独立上限2分钟（本地 paired suite42.333秒，避免1分钟上限的 CI 速度波动；数值执行仍900秒）。上传仅每个 placement 的 summary.json、progress.json、source_hashes.json；summary 的固定上限为98,304字节，覆盖两case全部有界诊断；固定有限误差/阈值、布尔语义、哈希与安全错误分类。所有原始张量、weights、完整 RESULT、producer日志和私人路径不上传。没有 Public/full-block/RTL 执行。

冷检查：

    python -B -m unittest candidates.qwen2_resident_matrix.raw_kv_native_qk_run.test_runtime candidates.qwen2_resident_matrix.raw_kv_native_qk_run.test_phase candidates.qwen2_resident_matrix.raw_kv_native_qk_run.test_run_ci candidates.qwen2_resident_matrix.raw_kv_native_qk_run.test_dispatch_capture candidates.qwen2_resident_matrix.raw_kv_native_qk_run.test_dispatch_diagnostic -q

另以 `python -B -O` 重跑。冷测试、clone/compose 来源证明与实际 native 验证分别报告。

官方诊断 API 来源：
- https://raw.githubusercontent.com/pytorch/pytorch/v2.10.0/torch/backends/mkldnn/__init__.py
- https://uxlfoundation.github.io/oneDNN/v3.7/dev_guide_verbose.html

`verbose` 的进入/退出只调用 verbose 开关；与独立的 backend flags setter 区分。运行时还检查 mkldnn.enabled 未改变；这些 source/control 检查不是新的 numerical PASS。
