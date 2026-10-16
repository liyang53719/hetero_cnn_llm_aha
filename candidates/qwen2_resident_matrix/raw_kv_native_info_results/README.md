# Native16 information-record 部分失败证据

## 中文计划与当前结论

- 已完成：核对 run 38941569876、placement 1、job 117110232158、artifact 12062928370；执行 commit 为 `331d428872946a3341c173823c6fa7f416600401`。原始 ZIP 为 `dispatch-info-record-failure.zip`，SHA-256 为 `a30c1dbdc35a320d6eaa1b5fecc10a41c93e0bf82e101d897eef4c68728fcaae`，恰好包含三个安全 JSON。
- 已完成：native16 原始数值结果为 `PASS_BF16_STAGE_BUDGET`，29 个阶段、28 项分配的 BF16 检查通过，两种模式各九项语义检查全部通过；FP32 仍仅为诊断。原有 QKV/QK 算术、recipe、门限和舍入顺序不变。
- 失败：native16 诊断仍为 `INCOMPLETE_DIAGNOSTICS`。BF16 捕获有 9 条识别的 matmul、6 条 info、1 条 unsupported，共 16 行；唯一非零 rejection reason 为 `information_record=1`，malformed=0，未截断。整体状态保持 `FAILED`，耗时 56.418942 秒。
- 未运行：native128。summary 的 `[16, 128]` 只是请求序列，native_results/native_diagnostics 只有 native16。Public、完整实际执行链与 RTL 均未执行。
- 下一步：独立审查 information-record 解析及诊断后的继续执行控制，并通过冷测试。后续修复与执行使用新的来源身份；本次历史失败不被改写，不能由未来的解析器修复补成 PASS。

## 观察与推断边界

六组已识别 BF16 execution 按原顺序为：DENSE_HIDDEN ×1、QKV_KV ×2、QK ×1、PV ×1、DENSE_HIDDEN ×1、MLP ×3，共九条。保留两个独立 DENSE_HIDDEN 记录，不以 role 为唯一键合并。所有 implementation 为 `brg_matmul:avx10_1_512_amx`。安全报告不包含原始 post-op 文本，也不能仅由 DENSE_HIDDEN 形状进一步唯一命名算子。

唯一 unsupported 的分类是 `information_record`，并非 `information_header`；该分类不能确定具体缺失行。原始日志未保存，因此本 checkpoint 不声称已找出那一行的内容或根因。已识别 execution 不足以把观察完整性提升为通过，也不证明不同 host 的 dispatch 或数值差异具有因果关系。

CPU 的 11 项 flags 均为 true，包括 AMX BF16/INT8/TILE、AVX512 BF16；eligibility 仍不等于 backend qualification。oneDNN 版本为 3.7.1、commit `8d263e693366ef8db40acc569cc7d8edf644556d`。双库加载前后、recipe 前后及 gate 后的 x87/SSE rounding 均为 0，FTZ/DAZ 均为 false，四项 fenv change 均为 false。这里只确认记录的控制状态未变化。

FP32 scope 为 `NO_ONEDNN_EXECUTION_OBSERVED`，execution/info/unsupported 及所有 rejection reason 均为 0；不据此推断其他 backend。native16 数值/诊断的局部 postflight=true 与 summary 整体 postflight=false 分开保留。

## 保存内容与冷检查

本目录仅有 `EVIDENCE.json`、`README.md`、`test_evidence.py`。前一次 `raw_kv_native_dispatch_results` 保持不变。EVIDENCE 完整保存安全 summary/progress，包括全部 native16 阶段、语义、两模式阶段双方哈希、13 项输入哈希及库/build/CPU/fenv/capture。source_hashes.json 保留精确成员 SHA、完整对象与 252-source map 的 canonical digest、10 项 generated map、13 项历史运行层来源和 21 项冻结 recipe/输入来源，避免重复展开完整来源清单。

历史 runtime/contract/parser 哈希只绑定原 artifact，不要求与当前修复源码字节相同。冻结 recipe、原始 gate、loader、数值契约及 13-tensor pin ledger 继续核对当前文件。原 summary 中 source_manifest_sha256 与上传 source_hashes.json 的成员 SHA 是不同对象的身份，不混用。

从仓库根目录执行：

    python -B -m unittest candidates.qwen2_resident_matrix.raw_kv_native_info_results.test_evidence -q
    python -B -O -m unittest candidates.qwen2_resident_matrix.raw_kv_native_info_results.test_evidence -q

八项测试只用标准库读取 JSON/ZIP/文件并核对身份与部分失败语义，不导入数值模块，不编译，不运行 native，不触发 CI 或下载。

默认只在本证据目录寻找同名 ZIP；也可设置 `RAW_KV_INFO_ARCHIVE` 为已有原始 ZIP 的路径。默认 ZIP 不存在时，仅原始 ZIP 字节核验一项明确跳过；显式指定的路径不存在则失败。无 ZIP 的测试通过不能声称重新验证了 archive。交付时使用已有原 ZIP 跑 normal 与 `-O`，确认该项未跳过。

本记录不是新的 numerical acceptance、backend-order proof 或运行授权。
