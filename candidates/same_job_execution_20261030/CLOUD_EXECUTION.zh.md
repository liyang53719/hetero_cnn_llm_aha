# GitHub 构建 / 本云执行分层接入（TEMP，源码候选，未发布/未执行）

用户 2026-10-31 13:32 明确要求 GitHub 不再承担完整验收。本候选沿原真实路径拆开构建者和执行者，绝不以 GitHub 源码/构建 PASS 冒模型或 RTL 数值 PASS。

## 已实施路径

- 构建仍用原固定 4096 MAC、五 profile 同一生成 SV/同一 ELF；本 split 工作不新增或认证 Vector32 全链 II=1/性能，实际硬件定义保持原冻结源码；GitHub 仅编译、链接及冻结七文件。原 bootstrap 本身无 AVX512 门，P0 AVX512 约束属于原参考运行时，不是编译器的硬件要求。
- `prepare_cloud_execution.py → controller/cloud_flow.py → runtime.install_job 或 runtime_reuse（明确预算选择） → owner/reference → numeric_tail → provider.prepare → connect_owned → consumer_owned → dut_evidence → required_acceptance → summarize_cloud_execution`。
- 云端沿原 70 权重完整数据与五参考链、M128 完整刺激和比较；53 archives/3 runtimes 可显式原地复用，参考必须 fresh 验证；不缩 4096、不换参考、无单 token 冒 chunk。各真实资源阶段仍受原严格 supervisor/cleanup/EOF/gzip 门约束。
- builder 保留真实 GitHub 六字段身份。executor 独立 UUID、boot ID、真实 controller PID/start tick、开始时钟、实际 host receipt SHA。绝不伪造 GITHUB_RUN_ID 或把导入包改成 same-job retained result。
- 原 same-job 分支与历史证据保留。云端不采用 CI 的 21000 秒上限；完整生命周期仍必须有独立批准的有限预算、清理余量和当前资源准入，缺输入先拒。
- 外部 operator-reviewed approval SHA 从受信调用者给入，不从文件自身读取当信任根。审批绑定 source、真实 artifact manifest、执行 UUID、host、budget、用途和独立 review evidence；实际 invocation 不可变落盘、summary 离线重算。这样 actual-artifact budget 不写回 builder 源码，避免无穷重建循环。
- Calibration 最多原 300 秒 × 五块；FULL 另需实际校准及独审完整预算，不能只改 label/timeout。所有数值资格仍由原逐项完成/严格位比较/外层 cleanup 重算。

## 七文件与传递边界

固定名称：`dut.bin, hardware.sv, driver.cpp, source_manifest.json, tool_manifest.json, build_receipt.json, frozen_artifact.json`。总展开 ≤4GiB；包含同一生成 SV、一个构建 ELF、源码及有界元数据，不含权重、输入、参考、NPZ、IR/classes/rawlog。artifact_handoff 流式核原文件 bytes/SHA、实际 builder 身份/阶段来源及独立远端 receipt pin；文件本身不认证自己的作者。真实 API/source/run/artifact ZIP 校验由上层可信下载流程完成后提交明确 expected handoff SHA。

本候选没有上传或下载任何构建包，没有启动 CI 或 DUT。七文件经 GitHub Actions artifact 中转许可由 root 向用户确认；未获许可不上传。当前尚无新完整 ELF，所有产物大小/NEEDED/兼容性未知，不能借旧 PASS。

## ABI 与资源（未闭环，不隐瞒）

- 本阶段保留原严格 native loader/全部 resolved DSO 与构建 tool inventory 的真实 SHA/路径校验；不同云系统可能被拒绝。仅 x86_64、SONAME 或版本号不足以放行。
- 可恢复官方运行依赖可未来在 workspace 做原 loader+DSO 闭包；需同 bytes、实际 ELF 的 NEEDED/PT_INTERP/RPATH/符号版本及实际解析证明。未实现该重定位路径，未把它夹入七文件上传范围。
- 原 13GiB 是构建资源门，不当云端运行门；运行阶段各自锁内检查。未知旧 owner 5GiB 预约保留；不能回收/杀死未知进程或以当前低 RSS 擅自抹除预约。
- 低内存诊断候选：group RSS 采样上限仍独立声明，**不是 cgroup 硬隔离**。DUT 单进程 AS 可收紧不改硬件。consumer 在加载完整元数据/参考前先查真实 VmSize，再 soft512MiB/hardDUT ceiling；fork 后子设自己的 hard AS，Popen 返回后父立即 hard512MiB，Popen 失败也收紧。成功 Popen 后收紧异常在原 cleanup try 内，仍 kill/wait；不能把 fork 前 soft-only 窗口说成 hard512MiB。
- 原 1GiB 非 DUT 余量须覆盖 consumer/outer/helpers，不另叠加一份 512MiB。真正启动还需 ELF PT_LOAD/BSS/DSO/权重 mmap 账单、同时活跃父清单和持续资源检查；未填任何 actual-approved 预算。
- supervisor 仅把 `sha(read_bytes)` 改成等价流式 `file_digest`，不变 supervisor/caps/清理/数值语义，避免大文件哈希瞬时复制。

## 当前事实

原 run41163215771 在 AVX512 主机门早拒：未安装 runtime、未构建 ELF、未跑 DUT；没有周期/速率数据。本候选测试是 mock/synthetic/源代码一致性，不是硬件运行。五块 M128 完整数值 0/5，最终同刺激 RTL 0/5，完整 block 周期/有效 MAC 利用率未知。FP32 顺序、每步 BF16 舍入、Qwen2 FP32 存储、原 Torch 路由保持；MoE 小 ID 同分契约仍未获批准。

源码确有共享32-lane bank（`UnifiedVectorElement32BankV4.scala:22`，由 `UnifiedMoeSharedArithmeticAdapterV5.scala:45` 实例化）及其他ALU；不能将总ALU说成仅32，也不能从配置字段推导全链II=1或最终吞吐。

## 已接构建者和只读 runtime 复用分支

- GitHub 独立 build-only 薄入口复用原 bootstrap 7200 秒（包含 prep 的原 1800 秒紧门），不安装参考运行时/权重，不执行 DUT。150 分钟 workflow 包含 checkout/验证/导出；原阶段清理与资源门不变，不能保证所有最大耗时均能塞入预算。唯一 launch 尚不存在，七文件传递批准源锁为 `None`，guard/export 双拒绝。
- 离线 ZIP 接收仅在外部可信 API receipt SHA 与实际下载 ZIP SHA 明确给入后工作；API stored-size 与 downloaded byte 数分开，精确七件、展开 4GiB 上限、无 symlink、流式 rehash。所有文件0600，ELF不自动加执行权限；不下载、不运行。真实执行前需在可信包、ABI与资源准入审核后，显式对已验 `dut.bin` 赋 owner 执行位；接收动作本身不授予执行权。
- `IMPORT_EXISTING_PINNED_RUNTIME` 配对 `READ_EXISTING_PINNED_ARCHIVES`，独立预算批准清单 SHA。按原地完整树/sidecar/wrapper/解释器/官方53 archives 重新验字节，原 wrapper 下本 executor fresh import/smoke，生成新 IMPORT_VALIDATION_ONLY receipt；原 INSTALL 仅历史来源。每次 reference/consumer lease 仍前后重验原树，不改旧库/不硬链/不搬旧owner身份。
- 复用仍保留35B优先资源预检，再Qwen2/0.8B；profile映射/五块顺序不改变。清单、真实静态内存账单、实际库兼容、执行批准输入均未制造。资源不足保持 INCOMPLETE，所有当前源码轻测不计模型或RTL通过。
