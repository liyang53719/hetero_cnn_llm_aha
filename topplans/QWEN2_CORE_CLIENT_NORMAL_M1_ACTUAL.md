# Qwen2 Core：首次真实 normal_m1 时钟行为

- **PASS（实际限定）：**原Core/PackedClient的Verilator RTL，脚本Matrix/memory，4939 body+3 reset，408 OBS/12 heads、四请求口113 payload rechecks；单次normal_m1终态与独审通过。
- **边界：**不是仅编译/mock，也不是完整Matrix数值、M2/M3、128 RTL/full29或90%MAC通过。pre-edge max诊断未直接观测post值；8.26078%是控制phase占比，4531其余边沿非idle证明。
- 原FAIL/STOP、reset/初始化差异、canonical任务状态保留，整体不置done；此批不含新harness或未执行后继候选。

[证据/源码refs与复现边界](../candidates/qwen2_core_client_m1_actual/README_ZH.md)
