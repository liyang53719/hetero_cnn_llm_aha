# M1：150CPU诊断FAIL与两个实际栈点

- 已观察：约60秒PrepareAst/InferResets、约120秒PrepareAst/CSE递归结构hash；两点不是全程CPU profile，也不替旧600FAIL指定唯一根因。
- 实际结论：FAIL_CPU150，无READY/OBS/CASE成功；normal exit=null、cleanup reap=-9。信号门源码/共享anchor/receipt/dump支持诊断，但无逐次proc原始快照/syscall独立复现。
- 保持：原600FAIL、compile/CHIRRTL/完整128软件观测域与packet结果；canonical todo/ongoing/done不改，整体ongoing。
- 仅下一步计划：官方NoCSE可选注解尚未在本包执行或证明收益；无候选源/GO/优化采纳。
- 安全证据：[`candidates/qwen2_core_client_m1_diagnostic`](../candidates/qwen2_core_client_m1_diagnostic/README_ZH.md)。不发布rawdump/IR/JAR/输入或进程身份。
