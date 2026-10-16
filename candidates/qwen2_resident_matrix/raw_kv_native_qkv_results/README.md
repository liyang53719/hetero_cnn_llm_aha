# QKV recipe 实际验证记录

## 中文计划与已验证结果
- 已完成：2026-10-16 run38929805616 / job117070580446 在 commit84a30febcfd02db568f5b04add83bd2f06abf096 执行 fresh native16→native128；总耗时61.095016秒。
- 已完成：native16 通过原始完整阶段判据；同一 recipe/library 的真实 M16 RESULT 作为 native128 的 small_gate。
- 已完成：native128 的 QKV、RoPE 后 q/k、cache 和 repeat 输入全部 bit-exact。gate 最大误差0.015625、prob 0.000904083251953125、y 0.0078125，均通过原始预算。两种模式各九项语义检查全部通过。
- 未通过：native128 scores 最大误差16、logits 最大误差2；原始 operator max_abs 上限均为0.03125。均值检查通过，但不能抵消最大误差失败。整体状态仍 FAILED，第二个 placement 被正确跳过。
- 进行中：审计独立 QK reduction 与 BF16 舍入/缩放次序，准备独立、原始输入驱动的新 recipe。没有放宽阈值或复用官方输出。
- 待执行：新 recipe 的合成验证与再次 fresh native16→128 gate；须另行固定来源并审查。Public 数值执行与 RTL 均未在本次运行。

`QKV_NATIVE_EVIDENCE.json` 保存已核对 artifact 的安全指标与完整两组阶段/语义投影，并绑定 ZIP、三个原始 JSON、源码与库的哈希。它不是新的运行授权或成功凭证。

实际证据表明，原始独立 NumPy QKV 次序的差异已消除，剩余首次差异位于 scores。当前独立路径使用 FP32 NumPy matmul 后 BF16 舍入，再缩放并 BF16 舍入；仅凭最大误差不能判定具体 QK 累加次序或缩放实现。下游 gate/prob/y 的改善也不能替代 scores/logits 的未通过判据。

历史 frozen recipe 与执行 contract 不在此记录中修改。该记录单独保存，避免改变已运行源码身份。

冷证据检查：

    python -B -m unittest candidates.qwen2_resident_matrix.raw_kv_native_qkv_results.test_evidence -q

再以 `python -B -O` 重跑。此测试校验冻结证据和字段关系，不执行原生算术。实际 artifact 字节对照另由发布前审查完成。
