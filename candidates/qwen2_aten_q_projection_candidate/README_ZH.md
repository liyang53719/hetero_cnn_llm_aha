# 有界前缀诊断与独立算术候选

结论：旧 DUT 的已完成前缀产物，对新 ATen AVX2、mkldnn 关闭的官方
M128 前缀，六个已比较节点均通过原 BF16 单算子误差门。不能因 CPU
归约图不同，直接推断必须重构硬件以逐 bit 模仿 CPU。

原门保持 max_abs≤0.03125、mean_abs≤0.005，没有放宽或更新旧期望。
其中 QR 的196608个元素有26个逐 bit 不同，但 max_abs=0.0078125、
mean_abs约9.91349e-08，仍通过原门。RMS 输出逐字节一致。
额外 Q/K/V/RoPE 子链比较也均通过原门，全部有限。

独立8×8累加器软件候选只检查128行的8列，共1024个元素，与新官方
完整形状 Linear 的对应列逐 bit 一致；这只是算法诊断，不是 RTL、
Chisel 实现或4096 MAC硬件资源映射。原模型、旧 runner 和现有门均未改。

## 运行范围

- `model.py`、`kernel.cpp`：显式64个逻辑F32累加器和归约顺序。
- `probe.py`：新官方完整 M128 Q Linear；旧完成QR产物的新比较。
- `prefix_probe.py`：沿固定原 capture 的官方 AST 执行 RMS、三路完整
  M128 Linear、原 RoPE，比较历史完成前缀。没有 attention、FFN或整块。
- 默认不运行；真实诊断需显式 execute，并由外层150秒 timeout约束。
- 六native身份、4/1线程、AVX2与mkldnn关闭前后核验；本地Python身份
  与CI不同，不宣称平台等价。
- 历史产物核验终态、finite、完整ACK、原hash及输入。仅两个已披露
  的历史准入/审计文件发生变化，其余旧源码身份相同。
- 原始数据、完整收据、路径、逐张量hash与详细结果只保留本地work，
  不纳入发布。原失败整块attempt不会因这些前缀比较变为整块PASS。
- qraw/kraw/vraw没有官方pre-bias参考，本诊断不制造对应通过门。

## 小测试

在仓库根目录使用固定本地NumPy环境运行：

`python3 -m unittest candidates.qwen2_aten_q_projection_candidate.test_model candidates.qwen2_aten_q_projection_candidate.test_prefix_probe -v`

共9项小测试，包括默认无执行、bias前不能提前BF16、非法输入、
历史收据缺终态/缺ACK/hash漂移拒绝。部分测试编译并运行小型合成C++
算术，不运行模型或官方前缀。
