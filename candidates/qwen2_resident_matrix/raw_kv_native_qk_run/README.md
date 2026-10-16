# Fresh native QKV + QK 候选验证

## 中文计划
- 已完成：QKV-only fresh native16 PASS；native128 的 QKV/q/k/cache/repeat bit-exact，剩余 scores/logits 失败，真实证据已单独发布。
- 已完成：新 raw-QK128 高/低 pair-FMA 候选的19项冷测试与实际 C++ 微型合成验证；尚未证明实际 oneDNN primitive 等价。
- 已完成：本目录独立执行层、双库身份绑定、247-source/221-setup 闭包与60项冷控制测试 normal/-O。
- 已完成：真实 Git clone/compose/re-exec 来源证明，247-source/221-setup/10 overlays，阻止 NumPy/Torch 导入、CDLL 和 producer 子进程。
- 进行中：最终独立审查与发布准备。
- 待执行：重新获取固定官方输入，fresh native16→native128 原始全部阶段判据；M16 失败立即停止。当前没有本 profile 的实际 native 结果。

## 数值与来源边界

本 profile 组合两个独立、分别验证的库。旧 QKV recipe 保持已发布字节；新 QK 库只计算独立路径自己的原始 K128 dot，原始 BF16(dot)、除以 sqrt(128)、BF16(score) 保持不变。所有官方前向、softmax/PV/MLP、原始29阶段记录/28个 BF16分配判据、两种模式各9项语义和阈值均不修改。新生成脚本保持在私有 checkout 外，精确 SHA 固定。

M16 和 M128 使用同一 combined Recipe identity、两库/source/pins；原始 small_gate 必须验证本次真实 M16 RESULT。QKV-only 的旧 PASS 不能作为新 M128 prerequisite。安全阶段报告既保留 QK 库身份，也单独记录 QKV 库/receipt/pins 哈希；`backend_order_proven=false` 明示候选身份，不把有限实例结果宣称为通用 backend 等价。

原始221-source setup context 只服务未修改的 preflight/environment/acquisition。新 union contract 覆盖全部执行来源、两个 recipe、两份微型证据、本运行层及独立 workflow；每个子进程前后和最终收据前检查完整来源。十个原有 setup overlays 不变。源码只从当前事件 Git commit 本地 clone，不网络 fetch；原始 checkout 不覆盖。

## 预算和 placement

每个 placement 的绝对900秒从 clone/preflight前计时，跨 re-exec 不刷新。固定阶段上限 preflight20、environment120、acquisition420、kernel30、native16 60、native128 120秒；均受总剩余时间限制，保留5秒清理和1秒收据。两个 C++ build 串行，共享原来的30秒 kernel deadline；各自 sole-owner 清理 compiler 进程组，不产生嵌套 supervisor 竞争。原始 native 算术和包版本不变。

保留最多两个串行标准 ubuntu-24.04 placement。第二个只在第一个来源绑定的 package前 CPU_UNSUITABLE 收据被验证后启动；解析/来源/安装/backend/编译/数值失败均停止，不进行数值重试。必要 CPU flags 不是 backend 证明，原始 Torch/MKLDNN 严格 gate 继续执行，不设置 ATEN override。两次 CPU不合格必须整体失败。

工作流仅自身路径 push/main 或 manual，run_attempt1，单 job20分钟/执行16分钟。上传仅每个 placement 的 summary.json、progress.json、source_hashes.json；固定有限误差/阈值、布尔语义、哈希与安全错误分类。所有原始张量、weights、完整 RESULT、producer日志和私人路径不上传。没有 Public/full-block/RTL 执行。

冷检查：

    python -B -m unittest candidates.qwen2_resident_matrix.raw_kv_native_qk_run.test_runtime candidates.qwen2_resident_matrix.raw_kv_native_qk_run.test_phase candidates.qwen2_resident_matrix.raw_kv_native_qk_run.test_run_ci -q

另以 `python -B -O` 重跑。冷测试、clone/compose 来源证明与实际 native 验证分别报告。
