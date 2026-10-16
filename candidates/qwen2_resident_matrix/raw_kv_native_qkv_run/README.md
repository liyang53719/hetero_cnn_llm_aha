# 独立 QKV recipe：fresh native16 → native128 验证

## 中文计划
- 已完成：原始故障定位为独立 NumPy QKV 与 BF16 block/pair recipe 的差异；发布的微型 C++ 合成验证已通过。
- 已完成：本目录独立执行层、严格来源绑定，47 项冷测试 normal/-O 通过；真实 Git clone/compose 的 238/221/10 来源与上下文验证通过。
- 进行中：最终独立审查及发布准备。
- 待执行：重建官方 13 张量输入，运行 fresh native16，再以同一 recipe/library/runtime identity 的真实 M16 RESULT 为 small_gate 运行 native128。
- 待验证：完整阶段误差是否通过。下游 NumPy QK/PV/MLP 未被替换；可能仍失败。没有 Public/full-block/RTL 执行结论。

## 执行边界

本版本保留原始 `scripts/qwen2_layer0_model_gate.py` 与已发布 recipe 八文件的字节。独立生成的脚本位于私有 checkout 外，经过固定 SHA-256 校验后执行。其 runtime_identity 记录生成脚本自身的哈希，M16 与 M128 使用相同 recipe/library/source identity。原始完整 29 阶段记录仍保留，其中 BF16 有 28 个分配判据，softmax_fp32 是诊断项；两种模式各九项语义判据仍由原始 gate 判定。阈值与官方前向不变。

使用单独版本化 union source contract，包含原始 221-source setup 闭包、已发布 recipe 与本执行层。只复用原始 preflight/environment/acquisition 三阶段，原始 context 使用原来的 221 项；每个子进程前后另行验证新 union map。不会把此验证写成 ASSETS/SETUP readiness 或 Public 接受凭证。

## 预算与复现

显式 `--execute`，一次执行；总绝对 900 秒从 clone/preflight 前开始，跨 re-exec 保持同一时间原点。阶段上限为 preflight20、environment120、acquisition420、kernel30、native16 60、native128 120 秒，均受总剩余时间限制并预留 5 秒进程组清理及 1 秒收据时间。工作流 20 分钟，实际执行步骤 16 分钟；没有自动重试。编译直接由恢复后的 supervisor 调用已固定 kernel.build；仅该函数负责 compiler 进程组的 TERM/KILL/reap。调用时暂停外层计时器，函数返回或异常后立即在来源检查前恢复，避免双层清理竞争。

包与模型下载只使用原始已固定 producer：CPU Torch2.10.0、NumPy2.3.5、Transformers4.40.1 和原始固定模型 revision/13 张量校验。环境 backend 原始检查仍执行。所有 payload、原生导出、完整 RESULT、环境与日志只留私有工作目录。源仓库只本地 clone，HEAD 必须等于事件 commit，无网络 Git fallback。

工作流 push 仅监听自身 `.github/workflows/raw-kv-native-qkv.yml`，另有 manual 入口；仅 run_attempt1。固定三个上传文件为 summary/progress/source_hashes JSON。summary 只投影固定阶段名、有限误差/阈值、布尔语义和来源哈希；M16 失败会停止 M128，并保留同样安全的失败指标。错误信息只使用固定分类及经来源校验的相对 frame，不上传原始异常文本或张量。

准备测试：

    python -B -m unittest candidates.qwen2_resident_matrix.raw_kv_native_qkv_run.test_runtime candidates.qwen2_resident_matrix.raw_kv_native_qkv_run.test_phase candidates.qwen2_resident_matrix.raw_kv_native_qkv_run.test_run_ci -q

另以 `python -B -O` 重跑。以上是冷控制测试；真实安装、下载、native16/native128 在发布启动前尚未运行。
