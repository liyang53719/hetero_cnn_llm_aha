# Qwen2 core/client：四源编译与 selected-on CHIRRTL 小范围进度

- 已完成：一次实际4源→20 classes编译；一次 selected-on Chisel→CHIRRTL结构生成，345 modules/344 instances，独审无黑盒，4条W005警告保留。
- 已保留：独立探针副本并非原核心同字节；原PackedClient不改；行为准备r2/r3及旧1613 topReset STOP历史不覆盖。
- 本批不纳入：M1或任何行为/数值/SV/RTL/full29/硬件90%利用率通过；整体主任务保持 ongoing，canonical既有todo/ongoing/done不改。原完整128软件观测域与packet证据不降级，旧FAIL/TEMP不抹去。
- 证据与复现：[`candidates/qwen2_core_client_chirrtl_evidence`](../candidates/qwen2_core_client_chirrtl_evidence/README_ZH.md)。下一行为阶段须独立审查和准入，不能由此条自动启动。
