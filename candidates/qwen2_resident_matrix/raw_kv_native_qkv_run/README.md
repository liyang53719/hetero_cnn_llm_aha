# 独立 QKV recipe：fresh native16 → native128 验证

## 中文计划
- 已完成：原始故障定位为独立 NumPy QKV 与 BF16 block/pair recipe 的差异；发布的微型 C++ 合成验证已通过。
- 已完成：本目录独立执行层、严格来源绑定，56 项冷测试 normal/-O 通过；真实 Git clone/compose 的 238/221/10 来源与上下文验证通过。
- 进行中：最终独立审查及发布准备。
- 待执行：重建官方 13 张量输入，运行 fresh native16，再以同一 recipe/library/runtime identity 的真实 M16 RESULT 为 small_gate 运行 native128。
- 待验证：完整阶段误差是否通过。下游 NumPy QK/PV/MLP 未被替换；可能仍失败。没有 Public/full-block/RTL 执行结论。

## 执行边界

本版本保留原始 `scripts/qwen2_layer0_model_gate.py` 与已发布 recipe 八文件的字节。独立生成的脚本位于私有 checkout 外，经过固定 SHA-256 校验后执行。其 runtime_identity 记录生成脚本自身的哈希，M16 与 M128 使用相同 recipe/library/source identity。原始完整 29 阶段记录仍保留，其中 BF16 有 28 个分配判据，softmax_fp32 是诊断项；两种模式各九项语义判据仍由原始 gate 判定。阈值与官方前向不变。

使用单独版本化 union source contract，包含原始 221-source setup 闭包、已发布 recipe 与本执行层。只复用原始 preflight/environment/acquisition 三阶段，原始 context 使用原来的 221 项；每个子进程前后另行验证新 union map。不会把此验证写成 ASSETS/SETUP readiness 或 Public 接受凭证。

## 预算与复现

显式 `--execute`，每个 placement 总绝对 900 秒从 clone/preflight 前开始，跨 re-exec 保持同一时间原点。阶段上限为 preflight20、environment120、acquisition420、kernel30、native16 60、native128 120 秒，均受总剩余时间限制并预留 5 秒进程组清理及 1 秒收据时间。每个 placement job 为 20 分钟，实际执行步骤 16 分钟；数值执行没有自动重试。编译直接由恢复后的 supervisor 调用已固定 kernel.build；仅该函数负责 compiler 进程组的 TERM/KILL/reap。调用时暂停外层计时器，函数返回或异常后立即在来源检查前恢复，避免双层清理竞争。

包与模型下载只使用原始已固定 producer：CPU Torch2.10.0、NumPy2.3.5、Transformers4.40.1 和原始固定模型 revision/13 张量校验。环境 backend 原始检查仍执行。所有 payload、原生导出、完整 RESULT、环境与日志只留私有工作目录。源仓库只本地 clone，HEAD 必须等于事件 commit，无网络 Git fallback。

工作流 push 仅监听自身 `.github/workflows/raw-kv-native-qkv.yml`，另有 manual 入口；仅 run_attempt1。最多两个严格串行的标准 `ubuntu-24.04` placement：只有第一个 job 的来源绑定收据明确为包安装前 `CPU_UNSUITABLE`，第二个才启动。任意来源、解析、安装、backend 或数值失败均停止。最多一次 native 数值尝试；两次 CPU 都不合格时整个工作流失败。每个 placement 使用不同 artifact 名。固定三个上传文件为 summary/progress/source_hashes JSON。summary 只投影固定阶段名、有限误差/阈值、布尔语义和来源哈希；M16 失败会停止 M128，并保留同样安全的失败指标。错误信息只使用固定分类及经来源校验的相对 frame，不上传原始异常文本或张量。

准备测试：

    python -B -m unittest candidates.qwen2_resident_matrix.raw_kv_native_qkv_run.test_runtime candidates.qwen2_resident_matrix.raw_kv_native_qkv_run.test_phase candidates.qwen2_resident_matrix.raw_kv_native_qkv_run.test_run_ci -q

另以 `python -B -O` 重跑。以上是冷控制测试；真实安装、下载、native16/native128 在发布启动前尚未运行。

## 冷测试修订记录

首次工作流 38924938337 在冷测试阶段失败，未进入 native 执行。测试把 runner 的 monotonic uptime 减去 895 秒，在短 uptime 下产生负起点；生产代码正确拒绝。修订只把经过时间场景改为固定正时钟，fresh fixture 使用当前正起点，并覆盖 1ns/1s/10s/894s uptime。生产正起点、绝对 900 秒及清理预留检查不变。

## CPU placement 修订

实际 run38927717447 在 environment 阶段因严格 `cpu_avx512=false` 被拒绝；固定 NumPy/Torch/version/commit 与 MKLDNN 检查通过。线程配置是在失败点之后才执行，诊断中的前置线程 false 不表示线程配置失败。该次没有进入数值计算。

新 pre-package 检查只用标准库：在 5 秒上限内读取最多 2MiB `/proc/cpuinfo`，检查所有处理器 flags 的交集 `avx512f/avx512vl/avx512bw/avx512dq/fma`。只记录固定布尔字段与有界处理器计数，不记录 CPU 型号或原始 cpuinfo。缺少必要 flags 才产生 `CPU_UNSUITABLE`；文件缺失/格式错误、非 Linux x86_64、ATEN override、来源漂移或超时均为失败，不允许第二个 placement。

`ELIGIBLE_FOR_BACKEND_CHECK` 只说明具备必要 flags。原始 Torch `get_cpu_capability()==AVX512`、固定版本/commit、安装来源和 MKLDNN gates 仍须真实通过；没有设置 `ATEN_CPU_CAPABILITY` 来冒充能力，没有更换算术/阈值。

官方 [GitHub standard runner 说明](https://docs.github.com/en/actions/reference/runners/github-hosted-runners) 仅列 OS/架构/资源标签，未提供标准 AVX512 CPU 选择标签或型号保证。因此保留既有标准 runner，使用显式有界 placement；不新增付费资源或 self-hosted 配置。[PyTorch v2.10 DispatchStub](https://github.com/pytorch/pytorch/blob/v2.10.0/aten/src/ATen/native/DispatchStub.cpp) 的 AVX512 检测包含 VL/BW/DQ 和 FMA3；本前置 flags 检查不能替代其 OS/runtime 检测，也不保证 BF16 dispatch 或数值 PASS。
