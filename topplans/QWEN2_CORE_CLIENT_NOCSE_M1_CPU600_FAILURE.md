# NoCSE normal_m1 CPU600：真实失败保留

[本批精确证据](../candidates/qwen2_core_client_nocse_m1_failure/README_ZH.md)：原 17 + 新 3 类，在不改变原 600 CPU 与其他限制下独立运行，实际 CPU 预算 FAIL；没有 READY/OBS/CASE_PASS 或新的线程栈。

旧 CPU150 的 SymbolTable 观察不能推定本次 CPU600 热点，初始 LOW IR 相同 hash 不证明 prepared graph 相同；无行为、数值、RTL 或性能通过。旧 FAIL/STOP 与已有有限范围 PASS 不变，canonical todo/ongoing/done 不改，整体继续 **ongoing**。

下一步仅允许另审的有界后端路线准备；未执行的 SV 候选、配置、GO 或结果不在本批。不得自动重跑、加时或扩大成功范围。
