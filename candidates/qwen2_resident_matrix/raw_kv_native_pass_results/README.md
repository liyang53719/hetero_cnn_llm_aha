# Fresh native QKV+QK M16/M128 通过证据

## 中文计划与已验证结果

- 已完成：run 38944308159、placement 2、job 117120055314、artifact 12065025969；执行 commit 为 `fb64c97971ba5c6109051e7547f6a0d57a76f256`。ZIP `native-qkv-qk-m16-m128-pass.zip` SHA-256 为 `88d79cf4b74fb7bc5df60b4aed2383c1e1bf02bbbe18e5c59c3d41c1e4882689`，恰好包含三个安全 JSON。
- 已完成：v3 profile 的 fresh native16 与 native128 均通过原始数值判据，整体 `PASS_NATIVE_QKV_QK_M16_M128`，numerical_acceptance/postflight_complete 均为 true，耗时 65.347275 秒。
- 已完成：每个 case 都保留 29 个阶段、28 项分配的 BF16 检查及两种模式各九项语义检查，全部分配的检查通过；FP32 仍只作诊断。M128 prerequisite 绑定本次真实 M16 RESULT SHA，并共用两库、recipe、输入及来源身份。
- 已完成：两份诊断均为 `COMPLETE_DIAGNOSTICS`。M128 的 scores/logits 为 bit-exact；最终 y max_abs=0.00390625、mean_abs=5.5594719015061855e-6，保持原 block 上限 0.05/0.01。operator 上限仍为 0.03125/0.005；原算术、recipe、舍入顺序不变。
- 下一步：将本 checkpoint 作为当前 native 候选的有限通过证据。Public/完整实际执行链/RTL 的执行与验收另行处理，不由本次 native 通过自动覆盖。

## 精确 dispatch 范围

两次 BF16 scope 各有九条 matmul、七条 info、共十六行，unsupported/malformed 为零，未截断；所有有限 rejection reason/subtype 计数均为零。所有识别的 implementation 为 `brg_matmul:avx512_core_bf16`。CPU AVX512 BF16 为 true，AMX BF16/INT8/TILE 均为 false；不能将本次通过扩展成 AMX 路径通过。

M16 的六组记录按顺序为 DENSE_HIDDEN ×1、QKV_KV ×2、QK ×1、PV ×1、DENSE_HIDDEN ×1、MLP ×3。M128 保留相同六组计数，但两条方形 attention 记录均明确为 ATTENTION_SQUARE，不猜测其 QK/PV 标签。重复 DENSE_HIDDEN 记录不合并。FP32 为 NO_ONEDNN_EXECUTION_OBSERVED，不推断其他 backend。

记录的双库加载前后、recipe 前后和 gate 后 x87/SSE rounding 均为 0、FTZ/DAZ 均为 false，四项 fenv change 均为 false。完整 CPU/build/fenv/输入/阶段双方哈希保留在 EVIDENCE 中；诊断自身仍为 diagnostic_only=true、numerical_acceptance=false。

本次通过限定于记录的输入、M16/M128、v3 profile 和观察到的 host/backend。backend_order_proven、actual_chain_executed、public_executed、rtl_executed 仍为 false，不证明通用 backend 等价，也不证明此前 host 差异造成数值差异。先前失败 checkpoint 保持原样。

## 与前次 AMX native16 的有界比较

比较对象为 run 38941569876、commit `331d428872946a3341c173823c6fa7f416600401` 的 native16；用 `raw_kv_native_info_results/EVIDENCE.json` 完整文件 SHA 和原 ZIP/成员 SHA 绑定身份。前次没有 native128，因此不进行跨 run M128 对照。

原始冻结 gate 明确定义 actual_f32_sha256 为 native_forward、reference_f32_sha256 为 independent_forward。两次 13 项原始 tensor 哈希映射、canonical tensor-map digest、记录的 fenv 和 fenv change flags 相同；两个模式下全部 29 项 independent 阶段哈希均相同。native 哈希在 BF16 的 17 个阶段、FP32 的 24 个阶段不同，固定的相同/不同阶段名列表保存在 EVIDENCE 中，不保存张量数组。

BF16 native 不同阶段为 act、att、cache_v、down、gate、kr、n1、o、pv、q、qr、r、repeat_v、silu、up、v、y。FP32 native 不同阶段为 act、att、cache_k、cache_v、down、gate、k、kr、logits、n1、o、prob、pv、q、qr、r、repeat_k、repeat_v、scores、silu、softmax_fp32、up、v、y。

已观察的 implementation 从前次 `brg_matmul:avx10_1_512_amx` 变为本次 `brg_matmul:avx512_core_bf16`，CPU flags 也不同。backend_build 中只有 numpy_build_sha256 不同：前次 `ed35d13524a37699c63ae6cbfb7357bf6e1adb739d2d637339a9845d730b68e7`，本次 `23f9c5f718f899ff7113e2401b36c2b3c862f74c5a153011ac3d05d4a8b30451`；其余已记录 build 字段相同。因此不是仅改变 ISA 的受控实验，不能把 native 差异或本次通过唯一归因于 ISA，也不能把未观测的环境条件视为相同。

## 原始记录与冷检查

EVIDENCE 完整保留安全 summary/progress。最终 summary 是 PASS；progress 原文仍为 `TERMINAL_RECEIPT_PENDING`、phase=finalize，本记录不会将该较早状态改写为 PASS。最终判定来自实际终态 summary。

source_hashes.json 保存精确成员 SHA、完整对象和 252-source map 的 canonical digest、10 项 generated map、13 项历史运行层来源及 21 项冻结 recipe/输入来源，不重复展开完整来源清单。历史 runtime/contract/parser 哈希只绑定本次 artifact，不要求与后续修复字节相同；冻结 recipe/gate/loader/数值契约和 13-tensor pin ledger 继续核对当前文件。运行时 source_manifest_sha256 与上传 source_hashes.json 成员 SHA 分别保留。

从仓库根目录执行：

    python -B -m unittest candidates.qwen2_resident_matrix.raw_kv_native_pass_results.test_evidence -q
    python -B -O -m unittest candidates.qwen2_resident_matrix.raw_kv_native_pass_results.test_evidence -q

七项冷测试仅使用标准库读取 JSON/ZIP/文件并检查身份、fresh M16 gate 绑定、原始数值判据、dispatch 范围和跨 run 有界比较，不编译、不导入数值模块、不运行 native、不触发 CI 或下载。

本次 ZIP 默认只在本证据目录寻找；也可设置 `RAW_KV_PASS_ARCHIVE` 为已有原始 ZIP 的路径。前次 ZIP 可通过 `RAW_KV_PASS_PRIOR_ARCHIVE` 显式提供。缺少某份 ZIP 时，相应字节验证测试明确跳过；显式指定的路径不存在则失败。绑定前次 EVIDENCE 的比较测试始终执行。无 ZIP 的测试通过不能声称重新核验 archive。交付时同时提供两份原始 ZIP 跑 normal 与 `-O`，确认没有跳过。
