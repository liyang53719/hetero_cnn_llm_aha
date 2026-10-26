# Qwen2 Core：真实 normal_m2 限定里程碑

- **PASS（实际）：**原SV Core/PackedClient+脚本Matrix/memory，12143+3时钟、828 OBS、36零score、12次token1第二retire max+0；memory/PV由冻结执行harness被动断言链支持，非rawpacket重放。
- 当前cache/locale外置前后门已记录，旧pyc覆盖缺口不追认补齐。历史M1/M128/FAIL/STOP与canonical状态保持。
- 不证明j0/j1不同数据无alias、跨16边界、M3/full128/full29/FMA或90%MAC；6.818743%是phase占比，其余周期不是idle证明。整体任务不置done。

[精确证据层级及角色pins](../candidates/qwen2_core_client_m2_actual/README_ZH.md)
