# 独立自然 dispatch N0 候选实测：双 SHA 相等，未采纳基线

- 原 Actions run：[39252523415](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/39252523415)，attempt 1，job 118059594702，head `07bb63edae88a95ec4aadd28d2ebf6ee0e81768c`；原终态 success。
- 原三 JSON 保持逐字节原样，协调器总时长 18.262813 秒；这不是包含 checkout/setup/upload 的整个 job 墙钟。
- 实际独审：review_n0_dispatch_actual_39252523415_20261019T1236；MANIFEST.json 1032 B / f4adc0bb88800054fbf9aac77c9d84c8cd87009034aadb4e0009d2c76882bc38；SUMMARY.json 7225 B / 889efb81b48c3b7a50fbec0495511f912bac6dedb9b426324bc127f6a6e62ae6；ACCEPT_ACTUAL_INDEPENDENT_N0_NATURAL_AVX512_DUAL_SHA_EXACT_CANDIDATE_ONLY。此文件仅整理原证据，不进行新的下载、数值计算或原生作业。

## 实际记录的有限结果

四阶段分别为 wheels 获取 2.787410 秒、runtime 安装 8.409006 秒、固定 raw2 获取 1.076627 秒、独立候选 5.421418 秒；全部自然 exit 0、waitid 1/0、未超时、cleanup_confirmed=true，原 kill-before-reap 记录保留。

本次 capability_observed=true，expected 与 observed 均为 AVX512；11 项 reached/passed 全为 true，包括 source/raw2/native/environment/import/version/capability/thread/build/forward/postflight。冻结源的原 Python 3.12.14、Torch 2.10.0+cpu / NumPy 2.3.5、固定 native/source 哈希、4 intra-op / 1 inter-op、确定性、自然 dispatch 与对应 build digest 检查均按此成功路径完成。没有强设 ISA。

候选用原两项已固定 Range 输入（合计 789,504 字节），一次原官方 Qwen2RMSNorm forward；形状 `[1,128,1536]`、196,608 值及有限性门通过。原 BF16 393,216 B SHA `bd41672e6ea7d12746b41e56d21b3309369ecfd87cc26319ae6adbf0874e5cf2` 与 FP32LE 786,432 B SHA `3c25077e0b7aa5819df6fb93cbaba6a0d5379ac06b9df468beecd0f259b5cc3f` 的两项 exact 均为 true；没有放宽哈希或改用容差接受。

公开摘要为 AVAILABLE / CANDIDATE_EXACT_MATCH_ONLY，candidate 为 COMPLETE / CANDIDATE_EXACT_MATCH，父 boundary/type 为 NONE。采样 leader RSS 最大 308,408 KiB，限值 1,572,864 KiB；它是有限采样观测，不是 OS 硬限、整棵进程树峰值或逐时完整记录。

## 不扩展的资格边界

- `reference_accepted=false`、`baseline_adopted=false`，DUT/RTL/fullblock 相关字段全为 false。本次仅独立参考候选事实，没有自动替换原基线或接回 DUT。
- 不授予 Host N0 容差数值 PASS、单 RAM/AXI 退休、196,608 值 RTL 读回、权重进入 DUT 或 wholeblock 资格。
- 私有候选张量、原生成功日志、完整 receipt 与原始采样文件未包含在三份公开 JSON 中；本地只读汇总没有对这些未上传现物重新计算哈希。上述双 SHA 结果来自已固定执行源码及其严格安全报告。
- 前次 39248526073 只记录 capability != AVX512 的固定拒绝，未导出实际枚举。本次 AVX512 不倒填前次枚举，也不证明后续 hosted runner 会提供相同能力。前次 FAIL 原证据保留。
- 本小批仅三份原安全 JSON、此 README 和中文计划；不修改任何 workflow 或生产源码，不触发新的 Host/native 作业。文档 push 仍可能运行 guard。

## 原三文件身份

- `summary.json`：1653 B / `f81255b0805bb2bb7326c8d0ed89f152124290a63aaea9b7f2612ec754ebed98`
- `source_hashes.json`：6074 B / `252d43960a5546f6afb02b150c4905a2ad7284588cfd1ea0cfc8e0d24b3aa994`
- `stage_exits.json`：3115 B / `7d94b10434e627e17f2d12cd994f03874f26e499a6a2d17324ee605b02dd7e66`
