# 真实 Matrix CHIRRTL：声明级里程碑

状态：**PASS 仅实际 Chisel 构造 / common-namespace CHIRRTL / 声明 ABI 与有限接线文本核验**。证据与源码见 [`README_ZH`](../candidates/qwen2_core_real_matrix_chirrtl/README_ZH.md)。原 4096 路资源 FAIL、CPU FAIL/STOP 和主任务 todo/ongoing/done 原样保留。

本次单 FIR 19,551,779 bytes，375 定义 / 374 instance / 16 external；557 stage、1,398 pins 与清理链已审。4 个 W005 未隐藏。外部门仅历史 counts/pass/locale + root 确认原脚本逐项检查；launcher 事后归档，不是预绑定或历史逐项 hash 映射。

**尚未 SV、provider 执行、真实 FMA 数值、全 tile/非零参考、full128 RTL、full29、时延面积或 90% 有效 MAC 周期利用率通过。** 下一阶段需要新的冻结、独审和有界准入；本批不包含未执行候选，不将 M17 scripted 行为转移为真实 Matrix 通过。
