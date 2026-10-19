# 本地 historical 原 N0 参考资格通过（仅参考，2026-10-19T1320）

## 原始事实
这是当前 dot 云环境中的一次本地探针，不是 GitHub Actions 作业，没有 CI run URL。源提交 b507977022695113de2070f2a214f32189aeb582。保留原三份安全 JSON 原字节；本目录不含私有 tensor、runtime、原始日志或系统清单。

外层原 invocation 退出 0，用时 59.096539 秒；原协调器用时 58.951018 秒，二者口径不同。四阶段均自然退出 0、waitid code/status=1/0、timeout=false、cleanup_confirmed=true、kill-before-reap 已记录、final_reap_signal=null：
- 固定 11 wheel 获取：47.519585 秒。
- 固定离线 runtime 安装：4.426023 秒。
- 既存精确 raw2 只读身份：0.051432 秒。
- 原 n0_reference.py historical profile：6.400553 秒。

安全摘要为 LOCAL_REFERENCE_EXACT_ONLY、observation_state=AVAILABLE；原参考报告 PASS_FROZEN_N0_EXACT / COMPLETE / code=null、worker_accepted=true，自然 capability=AVX512（expected=AVX512），native_exact_reported=true、fp32le_exact_reported=true。父验收固定源码还要求原成功收据、参考 RSS、FP32LE 文件重读、raw2/source 后验同时通过。sampled_leader_max_kib=300024，验收限 1572864 KiB；这是 leader 采样观察，不是 OS 硬 RSS 限，也不包括后代。

## 固定来源与资格边界
使用原 PINS 已存在的 historical CPython：30,894,944 B，SHA256 fa67443527ed9647f760d807e2a38f26340757123e643c4639cf273ed15d5ea7，版本前缀 [3,12]。与 CI ci31214 身份分列；没有放宽原 AVX512、五库/构建、4 intra-op/1 inter-op、原官方一次 forward 或输出合同。

已冻结验收值可公开：原 BF16 393,216 B / bd41672e6ea7d12746b41e56d21b3309369ecfd87cc26319ae6adbf0874e5cf2；原 FP32LE 786,432 B / 3c25077e0b7aa5819df6fb93cbaba6a0d5379ac06b9df468beecd0f259b5cc3f。这里的 native 双 SHA 通过是原 worker 报告和固定门结果；writer 没有重新执行 forward，也不把它写成独立重读成功 BF16 文件（原 worker 成功时仅保存 FP32LE）。本轮私有现物独审结果见下文。

raw2 是既存已固定两资产的只读身份验证，共 789,504 B；本次未重新下载 raw2，没有改变其原目录，新的本地身份收据不冒充原 CI same-job 下载收据。

scope 精确保留：local_reference_qualified=true；baseline_adopted=false、dut_executed=false、fullblock_executed=false。该结果不是 RTL N0 数值通过、没有 Host/DUT 推进、不授 fullblock；不把本次自然 AVX512 回填更旧未知 ISA，也不改变已保存 39255764538 自然 AVX2 拒绝事实。预算仍是 600 work +120 安全尾，未增加预算或自动重抽。

父记录的更早 bwrap 环境初始化失败发生在用户代码启动之前，START/log/output 尚未创建；这是执行环境启动失败，不是已开始 native 的第二次运行。实际计算只有本次原 invocation。

## 独立审计与发布
实际独审：review_local_n0_historical_actual_20261019T1326，MANIFEST.json 848 B / 73979f6760b463d612bbbcc4176e1bd0fcbe653d436a773e49ccfe7a3f8e1277；SUMMARY.json 5431 B / d01bc4c5a43eff0248ee4ae4854dfed849cf1c31ae30bcbc5811f7acd4fc1b2d；ACCEPT_ACTUAL_LOCAL_ORIGINAL_HISTORICAL_N0_REFERENCE_EXACT_ONLY。

独审已只读重 hash 本次私有 FP32LE 全文件，核 196608 个值的低 16 位全零及有限位，并由高 16 位反投影 BF16 得到精确 bd41672e6ea7d12746b41e56d21b3309369ecfd87cc26319ae6adbf0874e5cf2；原五库、historical Python、四源码、两 raw、11 wheel 的重 hash 均同。这是现物字节/位检查，不是重算参考或读取另存的原生 BF16 文件。

此前 SOURCE 审 review_local_n0_historical_probe_source_20261019T1315：M 8c92ad8835d4517a770ed11ccccd7ce67b369c29af0cd9fe6c077eb12407af51 / S a8316aeae7f24e110740413dcccc7d4e3b996707d6517cb9e99e732ab2c29f85，范围仅本地原参考四阶段。

本批仅三原安全 JSON、本说明和中文计划完整文档替换；不改源码或 workflow，不触发新的 Host/native 作业。普通 guard 可运行。
