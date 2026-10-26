# Qwen2 Core：真实 normal_m17 跨 16 限定里程碑

- **实际 PASS**：原 SV Core/PackedClient＋脚本 Matrix/memory，404951+3时钟、8964 OBS、216groups、1836零score；12 heads均base0→16，尾local0/global16/max+0，prefix0..16。
- memory32640/PV14688是已执行被动断言＋编入表＋完整计数/exit0链，不是rawpacket独立重放。当前56门沿用M3来源，不声称新47cache实际读取，不回填历史Python缺口。
- 条件成功body下界106884与实404951并列，**不是效率比**；phase2.213601%非MAC，剩余395987非idle证明。真实跨16控制不排除同零值alias，不是realMatrix/fullFMA/full128/full29/fullprefill/90%MAC。
- 原FAIL/STOP与旧有限PASS、canonical任务状态保持；整体任务不置done。不纳未验收realMatrix候选。

[精确证据层级、资源与复现引用](../candidates/qwen2_core_client_m17_actual/README_ZH.md)
