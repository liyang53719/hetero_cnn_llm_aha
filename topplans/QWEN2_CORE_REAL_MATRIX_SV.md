# 真实 Matrix common SV 里程碑（有限 PASS）

实际官方 firtool 一次生成 SV 已独审：38 definitions / 118 instance declarations，选定 shell 31 definitions；限定声明 ABI 与接线文本通过。详情见 [`README_ZH`](../candidates/qwen2_core_real_matrix_sv/README_ZH.md)。仅公开小源、可重建声明期待、pins/hash/必要摘要，不上传 48 MB SV、FIR/ELF 或数据。

保留 1 条未处理 DedupGroup warning，不能按 warning 行数推残留数或无害性；旧 CHIRRTL 4 W005、4096 资源 FAIL、CPU FAIL/STOP 不变。新 launcher 预绑定和 expected+ck-pass 收据不倒填旧外门历史。

**仍未 provider 实现、非零数值、clocked 行为、4096 fit、full128 RTL/full29或90%有效 MAC 通过。** 本批不改 canonical 状态、不将整体置 done，不包含未执行后继候选；下一步必须重新冻结、审查和有界准入。
