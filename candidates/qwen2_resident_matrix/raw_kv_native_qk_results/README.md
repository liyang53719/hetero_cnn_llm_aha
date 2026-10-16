# QKV + QK native 实际失败证据

## 中文计划与当前结论
- 已完成：run 38934796546、placement 2、job 117087788071、artifact 12059689836 的三个 JSON 与 ZIP 哈希核对。执行源码为 commit `cacc320580ca93dd7d70d4b3129b5522531bb66f`；运行耗时 60.566867 秒。
- 已完成：fresh native16 通过原始完整阶段预算，其真实 RESULT 哈希与 native128 的 M16 gate 一致。两组报告各保留 29 个阶段、28 项 BF16 预算检查与两种模式各九项语义检查；语义检查全部通过。FP32 仍仅为诊断。
- 未通过：native128 的 gate / logits / prob / scores 最大误差分别为 0.041015625 / 0.5 / 0.031494140625 / 16，均超过原始 operator 上限 0.03125。整体状态保持 FAILED，不能用均值通过或最终 y 通过替代阶段失败。
- 进行中：先定位本次上游 qr/kr/v 差异，再核对同输入下 QK reduction 与 BF16 缩放、舍入顺序。原因尚未确定；本 checkpoint 不修改 recipe、门限或已运行源码。
- 未执行：本 checkpoint 只整理证据并运行冷完整性测试，不执行新 native 算术、Public 数值路径或 RTL。原运行的 Public/RTL 执行标记也均为 false。

## 与前一次 QKV 验证的比较边界

前次 `raw_kv_native_qkv_results` 记录 run 38929805616：M128 的 qr/kr/v 及 q/k/cache/repeat 输入 bit-exact，仅 scores/logits 超预算。本次与前次的 QKV ELF 哈希相同，均为 `713d998af455257a052b5fb1a0758d1a8da8273cd6e93c65d956d1f032a60b7f`，但本次 qr/kr/v 在 M16 已出现非零误差，最大值分别为 0.00048828125 / 0.00000035762786865234375 / 0.00006103515625；M128 分别为 0.00390625 / 0.0078125 / 0.001953125。

因此，这两次运行没有建立上游完全一致的 QK 单变量对照。logits 最大误差由 2 变为 0.5、scores 仍为 16，只是报告中的数值变化，不能据此声称 QK 单独改善或退化。相同 ELF 也不足以确认运行配置、调用或数值路径完全相同。

原始 `scripts/qwen2_layer0_payload.py` loader 检查 13 个原始 tensor 的字节数与固定 SHA-256；payload manifest 同时包含 HTTP receipts。两次 manifest 哈希不同，本身不能证明原始输入漂移。此处核对了冻结 loader/pin ledger 的源码身份，没有重新审计两次原始 payload 字节，也没有把 receipt 差异认定为根因。

## 保存内容与冷检查

`EVIDENCE.json` 原样保存 artifact 内 native16/native128 的安全报告，并记录 ZIP、三个原始 JSON、选定源码、库、RESULT、生成模块与前次证据的身份。原 summary 的整体 postflight=false 与两份 native 报告的局部 postflight=true 分开保留，不能混同。

    python -B -m unittest candidates.qwen2_resident_matrix.raw_kv_native_qk_results.test_evidence -q
    python -B -O -m unittest candidates.qwen2_resident_matrix.raw_kv_native_qk_results.test_evidence -q

三项冷测试只检查证据哈希、真实 M16 gate 绑定、未放宽的失败与比较边界，以及冻结来源和 13 项 tensor pin inventory；不会导入或运行 native 算术。保存记录不是新的执行授权或验收成功凭证。
