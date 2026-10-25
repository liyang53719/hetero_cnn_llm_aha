# Qwen2 Core：官方 Verilator lint-only 证据

- **PASS（限定）：** 固定原始 SV 的官方 Debian 5.032-1+b2 lint-only，实际退出 0、预算/身份/清理通过；仅默认启用 warning，未 -Wall，无 -Wno。
- **旧 FAIL/STOP 保留：** 官方包首次提取 FAIL 后 r2 复用同包恢复；SV 原外层 checker FAIL、离线 r1 FAIL/r2 STOP、全部 Treadle CPU 失败不改。
- **未完成：** 没有持久 C++ codegen、build、模拟时钟、M1/完整128 RTL 数值、full29 或有效 MAC 周期利用率证明。日志内部 30 C++ / 22.763 MB 是 lint-to-null 计数；实际仅 3 文件 12,692 B 和 4 空目录。
- **下一步边界：** codegen/build/behavior 必须分阶段独立冻结、审查、准入；本包不含未执行候选，不预测其资源成功率，不替换 canonical 清单状态。

源/role pins/独审投影：[最小证据包](../candidates/qwen2_core_client_verilator_lint/README_ZH.md)。
