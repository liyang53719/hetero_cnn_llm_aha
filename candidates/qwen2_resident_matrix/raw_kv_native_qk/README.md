# 独立 QK128 pair-FMA 候选

## 中文计划
- 已完成：前一 QKV recipe 的真实 native16 PASS；native128 输入 q/k 等 bit-exact，但 scores/logits 仍失败，证据保存在相邻 raw_kv_native_qkv_results。
- 已完成：只替换独立参考的原始 K128 点积，明确采用64组高元素先、低元素后的 FP32 FMA；一个点积一个累加器。
- 已完成：19项冷准备/边界测试 normal/-O 通过，精确有理数 oracle 的 cancellation/tie 合成验证通过；实际有界 C++ 微型验证通过。
- 待执行：独立来源固定的 fresh native16→native128 全阶段验证。当前没有新数值 PASS。

这是待验证的 backend-scoped 候选，尚未证明等同于实际 oneDNN 所选 primitive 的归约次序。PyTorch 的 BF16 bmm 可进入 oneDNN；原始独立路径使用 NumPy FP32 matmul。QKV 的 K1536 两块次序通过，不足以证明 QK 的 K128 次序。已有硬件参考的16-stripe/fold/倒数乘法保持不变。

候选只接收独立路径自己的 q 与 repeated_k，返回未进行 BF16 舍入的 FP32 点积。不读取官方输出、原生中间值或 gate 结果。原始 gate 继续执行 BF16(dot)、除以 math.sqrt(128)、BF16(score)，mask、softmax、PV、MLP、官方前向和全部阈值保持原始字节/AST。FP32 模式及未启用候选的路径不变。

旧 QKV recipe 和原始 model_gate 文件不修改。新生成脚本先应用已固定 QKV patch，再应用本目录 patch；新精确 Recipe 组合旧 QKV 库和新 QK 库，其完整身份同时绑定进原始 M16→128 small_gate。旧 library 单独验证。本目录 pins 绑定两个 recipe 的执行来源；导入不编译、不加载原生库。

源准备检查的 AST 还原证明禁用分支保持原始行为，不能单独证明启用分支数学正确；启用分支依靠逐行审查、精确生成文件哈希和独立合成测试。拒绝非有限或非 BF16 输入、错误几何/别名、非默认舍入/FTZ/DAZ，出错不发布部分输出。

参考源码：[PyTorch v2.10 bmm dispatch](https://github.com/pytorch/pytorch/blob/v2.10.0/aten/src/ATen/native/LinearAlgebra.cpp)、[BF16 scalar division](https://github.com/pytorch/pytorch/blob/v2.10.0/aten/src/ATen/native/cpu/BinaryOpsKernel.cpp)。这些来源没有确立本次运行实际选中的 QK primitive。

C++ reference 使用最多786432字节的事务性输出暂存，成功后才拷贝到调用者；这是主机参考程序的内存，不是新增硬件 SRAM，也不提供硬件资源或周期结论。

## 微型实际验证

`SMOKE_EVIDENCE.json` 保存实际编译/执行返回码、源码/库/结果哈希和计数。一次显式30秒上限内完成 rows16/128、12 heads、K128 的199680个 FP32输出字逐位检查；49组精确 Fraction fixture pairs，23次 ABI调用，其中21次错误拒绝，含舍入环境恢复。没有模型权重。该结果只确认候选自己的明确次序与 ABI，不证明 oneDNN 等价，也不是完整 native16/native128 gate。

冷测试命令：

    python -B -m unittest candidates.qwen2_resident_matrix.raw_kv_native_qk.test_kernel candidates.qwen2_resident_matrix.raw_kv_native_qk.test_recipe -q

另以 `python -B -O` 重跑。实际微型验证通过显式调用 test_kernel.run_native_smoke，并使用外部30秒超时；unittest discovery 不编译、不加载库。
