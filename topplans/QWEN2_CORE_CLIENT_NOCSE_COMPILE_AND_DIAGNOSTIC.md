# NoCSE 单 Spec：编译 PASS，CPU150 实际诊断 FAIL

参见 [精确源码、类选择与实际证据](../candidates/qwen2_core_client_nocse_diagnostic/README_ZH.md)。唯一源码 delta 是第 33 行 59 B 官方 annotation；真实单源编译产生新 3 类，诊断使用原 17 + 新 3，未改变硬件、刺激、阈值或 clock 上限。

真实 CPU150 诊断仍 FAIL、无 READY/OBS/CASE_PASS。120 s 样本进入 SymbolTable pass1，而原样本在 PrepareAst/CSE；仅有阶段观察，不是因果速度、完成率、行为/数值/RTL PASS。相同初始 LOW IR hash 不证明 prepared graph 同大小。两样本、逐次 signal 证据和 CodeSource/annotation hit 缺口完整保留。

主任务继续 **ongoing**；canonical todo/ongoing/done 不变，所有旧 FAIL/STOP 保留。新 CPU600 计划和未执行候选不在本批；后续须独立精确审核与授权，不能把本诊断当作采纳优化。
