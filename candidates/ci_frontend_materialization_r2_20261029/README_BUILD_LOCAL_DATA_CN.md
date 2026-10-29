# BUILD_ONLY_LOCAL_DATA / NO_PAYLOAD_UPLOAD（TEMP）

该变体复用已审 794a89cc 源提案的实际 frontend、五段 O0 archive/link、完整物理来源闸门和本地七文件生成；不修改硬件、源码固定集合、参考或资源上限。唯一新 scope 是 FIXED4096_VECTOR32_BUILD_ONLY_LOCAL_DATA。启动路径 ci_launch/fixed_build_local_data_20261029_once.json，schema BUILD_ONLY_LOCAL_DATA_ONE_SHOT_V1，nonce fixed_build_local_data_20261029_once。

工作流只有一次 upload-artifact，路径仅 build-only-summary.json（64 KiB 安全摘要），保留 14 天。没有 binary/SV 上传 step，也没有 artifact upload gate；原 pack 内的来源/完整编译/ELF/hash 检查仍执行。本地 dut.bin、hardware.sv、driver.cpp、source/tool/build receipts、frozen_artifact.json 仅存在 runner 临时目录，不进行 API 上传、缓存、base64 输出或下载证明伪造。identity 中 artifact_name 只作既有本地 manifest 格式标识，**不代表上传存在**；不得生成 VERIFIED_GITHUB_ARTIFACT_DOWNLOAD receipt。

本变体只得到真实编译/链接终态与资源/错误摘要，不执行五块数值；完整 M128 仍 0/5。job 350 分钟、原 shared-tree/free/RSS/阶段上限不变，容量和编译成功未预先保证。不要将生成 ELF 冒数值 PASS。

依赖 794a 包中 22 个已审源文件及 cd26 测试布局修复；发布组合必须排除原公共 payload-upload workflow/guard/upload-gate（本变体无需它们），仅保留本文件列出的新工作流/guard/test/doc。原 794a 冻结包保持不动、公共上传决定仍 pending。source 发布与唯一单文件 activation 分开审；此提案没有 launch 文件，不自动启动。
