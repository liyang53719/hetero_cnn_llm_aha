# Qwen2 Core：C++ codegen-only 范围

- **PASS（实际）：** 官方 Verilator 原SV生成47文本文件27,712,886 B，独审8,859 public ABI /36 C++ Make源闭包/109 literal includes，资源/身份/清理通过。
- **PASS（仅源）：** 冻结2044 M1 harness的248源/合成控制；当前未编译或执行，不是行为PASS。
- **未完成：** build/link/simulation/M1数值/full128 RTL/full29/有效MAC周期利用率；`--assert`只生成选项，11.579 MB只是静态估计。原FAIL/STOP、canonical todo/ongoing/done不改。
- 下一步须独立build-only审查与准入，不在本包导入未执行后继候选或结果。

[原字节源、ABI重建与限定证据](../candidates/qwen2_core_client_codegen/README_ZH.md)
