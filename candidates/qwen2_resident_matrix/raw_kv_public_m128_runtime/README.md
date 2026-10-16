# M128 独立 setup 运行时来源层

## 中文计划

- 已完成的前置条件：真实 M16 Public21 observed-gates PASS、冻结 M128 preparation-only 组合与来源兼容映射。
- 已完成准备检查：独立 setup 变体、原始 native16→native128 生产器链、完整来源快照及 18 个普通 / -O 冷测试。
- 待完成：绑定 setup 与资产双凭据的数值准入、运行器和工作流。`authorize_run` 在本层始终拒绝 `launch_layer_missing`。
- 本层尚未执行下载、包安装、原生参考生产器或 M128 数值链。

本层先调用原封不动的已发布 preparation-only 组合，再应用两份零 fuzz patch。最终十个输出中，七个 M16 observer/transport/official-entry 输出字节完全不变；只对 assets、setup 和 ReducedPublicExecution 入口使用明确的新来源变体。M16 文件和先前 preparation-only guard 不被覆盖。

assets 与 setup 使用明确相同的完整闭合来源清单，而不是沿用旧 183/187 过滤。原始入口的来源并集必须等于这份清单。assets 的 loaded-source guard、setup 的 loaded-variant guard、所有旧不可变依赖、七个 base-verifier 身份以及 Git 中新监督器源码都继续校验；不会把生成的 overlay 冒充干净 Git 原文。

setup 总期限为 900 秒，含生产器清理与凭据提交。各阶段上限从同一剩余期限取最小值，不能相加扩展总预算。native16 与 native128 分别由原始监督器启动独立进程；native128 调用原始 run_gate 并提供真实 native16 small_gate。两者均执行原始 backend、payload、BF16/FP32 export 和语义校验。参考生产器仍是原始 sequential 与 block/pair 两种，使用真实 128 行 arena；各次参考执行上限沿用原始 45 秒。

计划中的下一层数值 work2400/external2430/outer3420/job60min 仍需独立准入与工作流审查。本层 source-ready 不代表资产 bundle 已建立、数值已运行或完整29节点已验收。私有 payload、张量、详细运行日志不得上传。

## 重现短测试

```sh
python -m unittest candidates.qwen2_resident_matrix.raw_kv_public_m128_runtime.test_runtime candidates.qwen2_resident_matrix.raw_kv_public_m128_runtime.test_setup_runtime -q
python -O -m unittest candidates.qwen2_resident_matrix.raw_kv_public_m128_runtime.test_runtime candidates.qwen2_resident_matrix.raw_kv_public_m128_runtime.test_setup_runtime -q
```

冻结 209 个来源输入，包含 pins 自身后为 210 个；严格生成十个 overlay。源码专用闭包测试实际调用组合后的 assets/setup helpers，并执行原始 entry/official source_hashes 的未改写 AST 与真实 prefix/fullgraph helper 链，结果精确相同。直接数值入口导入需要 NumPy，因此测试明确采用来源函数 AST 提取，阻止数值包和自定义 CDLL 加载；不替换 expected source map。
