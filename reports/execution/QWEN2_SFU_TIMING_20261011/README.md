# 原 SFU 源码时序与保存 gate 的分支证据

此目录只有复现源码、输入/源版本及哈希、计数和边界；没有 gate 原始张量、权重或编码 payload。

- `V0_SAVED_GATE_AUDIT.json`：原 v0 cold128 保存 gate。显式逐节点 FP32 NumPy 计算只到 denominator，宿主 FE_TONEAREST、全中间 normal/zero，66索引×19节点与独立整数RNE核对。未运行 reciprocal/SiLU完整输出。
- `V2_SAVED_GATE_AUDIT.json`：诊断 v2 cold128/carried128。BF16可表示 gate 去重后只计算各2156/2106项的原 exp7与denominator。
- `reproduce_v0.py`：原样保留本轮实际执行脚本；摘要内 `audit_script_sha256` 与此文件SHA相同。需要按原receipt恢复本地原始 gate；脚本不下载、生成或注入模型数据。执行方式：`python reproduce_v0.py --repo /path/to/repo --out /new/result.json`。

两份报告对应源码本身均已固定，不继承其他源码测试状态。V2复现入口是 `scripts/qwen2_shared_sfu_schedule.py --gate-result /path/cold/RESULT.json /path/carried/RESULT.json`。

这是 source-FSM 条件时序与 software-input 分支统计，不是完整Chisel仿真或RTL实测。v0及v2原数值FAIL保持，flags/异常接受未经证明。成功时序假定原flags策略未中断、接口连续ready及操作数已在寄存器；排除memory/ACK/owner控制成本。

说明与固定4096分母的上界见 [中文SFU说明](../../../doc/QWEN2_SHARED_SFU_SCHEDULE_MODEL_20261011_CN.md)。旧较松下界与新分支公式分别标版本；不推广到未观察的M/prefix。
