# Native dispatch 部分失败的冻结证据

## 中文计划与当前结论

- 已完成：核对 run 38938744221、placement 1、job 117100768160、artifact 12062251526；执行 commit 为 `48bf2e1f06df2aeb4e87e842dab25689d38849f9`。ZIP SHA-256 为 `521fe7411bbf643e045610e4142fa4a8fb29cf15903e464e4c8ba6293ad462bc`，恰好包含三个安全 JSON。
- 已完成：native16 原始数值检查为 `PASS_BF16_STAGE_BUDGET`，29 个阶段、28 项已分配 BF16 检查全部通过，两种模式各九项语义检查全部通过。FP32 仅为诊断。原有算术、recipe、门限和舍入顺序保持不变。
- 失败：native16 dispatch 诊断为 `INCOMPLETE_DIAGNOSTICS`。BF16 捕获有 4 条 unsupported、6 条已识别 execution、6 条 info，共 16 行；malformed 为 0，未截断。整体状态仍为 `FAILED`，耗时 67.926153 秒，不能以原始数值 PASS 覆盖诊断失败。
- 未运行：native128。summary 的 `[16, 128]` 是请求序列，实际结果与诊断映射只有 native16；不能将本次缺失的 M128 结果写成 PASS 或数值 FAIL。Public、完整实际执行链与 RTL 均未执行。
- 下一步：独立修复诊断语法并通过冷测试、来源审查；本证据保持历史状态。仅在本任务审查后的实际运行中才能取得新诊断结果，不将解析器修复视为本次运行已被补验。

## 已观察到的内容与推断边界

四组已识别 BF16 matmul 记录为 QK ×1、PV ×1、DENSE_HIDDEN ×1、MLP ×3，implementation 均为 `brg_matmul:avx10_1_512_amx`。artifact 内 CPU flags 包含 AMX BF16/INT8/TILE、AVX512 BF16 等且均为 true。CPU eligibility 不是 backend qualification。

保存的 oneDNN 版本为 3.7.1，commit 为 `8d263e693366ef8db40acc569cc7d8edf644556d`；还保留 Torch/build/官方源码哈希。双库加载前后、recipe 前后和 gate 后的 x87/SSE rounding 均为 0，FTZ/DAZ 均为 false，四项 fenv change 均为 false。这里只确认记录的控制状态未变化，不证明全部浮点行为或不同 host 的 dispatch 相同。

FP32 scope 为 `NO_ONEDNN_EXECUTION_OBSERVED`，零条 execution/info；这不识别或否定其他 backend。四条 unsupported 的原始文本未保存，本证据不能重建其内容或确认根因，也不能证明之前 host 的 dispatch 差异导致数值差异。已识别 AMX implementation 与 CPU flags 不能替代跨 host 的同输入、同配置对照。

## 保存内容与身份边界

`EVIDENCE.json` 完整保存三个原始安全 JSON 中的 summary/progress 对象；两者按原格式重建后可逐字节复核成员 SHA。其中保留全部 native16 数值阶段、语义、两模式阶段双方哈希、13 项输入哈希、库/RESULT/生成模块身份、CPU/build/fenv 和 capture 报告。

source_hashes.json 不重复展开全部 252 项来源映射，而保存原始成员 SHA、完整对象与 252-source map 的 canonical digest、10 项 generated map、13 项历史运行层来源与 21 项冻结 recipe/输入来源。原 summary/native report 的 `source_manifest_sha256` 是运行时另一个 manifest 身份，与上传成员 `source_hashes.json` 的 SHA 分开保留，不混同。

历史运行层哈希只绑定本次 artifact。当前诊断解析器、runtime、contract 可以有独立修复，测试不会拿其新字节冒充过去的源码。冻结 QKV/QK recipe、原始 gate、loader、13-tensor pin ledger 和数值契约仍与当前文件核对。summary 整体 postflight=false 与 native16 数值/诊断局部 postflight=true 分别保留；局部完成不代表整条流程完成。

## 冷检查

从仓库根目录执行：

    python -B -m unittest candidates.qwen2_resident_matrix.raw_kv_native_dispatch_results.test_evidence -q
    python -B -O -m unittest candidates.qwen2_resident_matrix.raw_kv_native_dispatch_results.test_evidence -q

八项测试仅使用 Python 标准库读取 JSON/ZIP/源码并核对哈希和报告关系，不导入数值模块，不编译，不加载或运行 native，不触发 CI 或下载。

ZIP 默认查找本目录下的原始 qk-dispatch-incomplete.zip（不纳入发布）；可设置 `RAW_KV_DISPATCH_ARCHIVE` 指向该原始 ZIP。若默认附件不存在，只有原始 ZIP 字节验证一项明确跳过，其余冻结记录检查继续；显式设置的路径不存在则失败。无附件的测试通过不能声称已重新核验 ZIP。本次交付应同时运行 normal 与 `-O`，并确认原始 ZIP 测试没有跳过。

这份记录只保存已有运行证据，不产生新的 numerical acceptance、backend-order proof 或执行授权。
