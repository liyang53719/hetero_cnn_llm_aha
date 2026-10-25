# SV 生成与有限结构恢复：不等同 RTL 行为通过

[本批源码/证据](../candidates/qwen2_core_client_sv_structure/README_ZH.md)：原 selected-on CHIRRTL 经固定官方 firtool native exit 0 生成留存 SV；原 outer checker FAIL、offline R1 FAIL、R2 source STOP 原样保留。R3 独立 Python-only 实际恢复通过固定文本的声明/top ABI/实例/声明存储门：25 modules、88 instance sites、8,859 top ports、4,921 个非空 named inputs；不是通用 SV 文法/表达式/中间 alias/数值/行为/时序验收。

公开最小 checker、固定 exporter 关键字来源、小合成测试和精确 ABI metadata 重建，不上传真实 SV、工具二进制或私有输入。未执行的 Verilator/harness 候选不纳入；硬件 MAC/系统 duty/90% 目标仍未知。历史 FAIL 与 canonical 状态不改，主任务继续 **ongoing**。
