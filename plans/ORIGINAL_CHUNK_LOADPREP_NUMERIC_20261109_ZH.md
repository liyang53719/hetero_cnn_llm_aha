# 原 Chisel prefill phase1 数值推进（2026-11-09）

## 目标与本轮范围

继续原五块 M128 prefill 数值链，固定 4096 Matrix MAC、8×512 与共享 Vector32 目标不变。本轮不重建完整 Host，不改生产算术、硬件配置、容差或既有未知运行的生命周期。五块完整原 Chisel/真实权重数值通过数仍为 **0/5**。

已核远端基线 main `70126e106fe213991511b5c668c3c04ee823a2db`。其 CI run `42245228906` 的 `source_compile_only` 成功只证明 204 个源码编译，未运行 elaboration、native 或 profile。保留原本地 `90b91a63` 的未发布候选，不把它们全部夹带进入本批。

## 新增实际证据

`candidates/original_chunk_loadprep_numeric_20261109/` 将原 `GdnRuntimeChunkLoadPrepV2Owner` 接入原 `HeteroFP32Alu` / HardFloat AddRecFN，通过 ChiselTest/Treadle 实际运行。编译输入包括 29 份完整原 Scala 文件和一份逐字提取的 receipt 类适配文件；所有来源均有 SHA256。

- legacy policy、runtime16、head0、M128 的 chunk0 和 chunk1 各完成 1,600 读拍、1,600 写拍、6,528 cycles。每块逐位比较 25,600 个 32 位字，共 51,200 字，包含零填充；Q/K/V 拷贝与累计 gate/beta 写回符合固定 scalar oracle。
- 四例运行随后触及预设 160 CPU 秒限制，SIGXCPU / exit -24，墙时 166.27 秒。guarded runtime16 没有完整案例，不计通过。
- 最终便携 harness 新增仅运行 guarded runtime32 的选项，使用 51,200 字节行与正确 role/gate 偏移。修改后源码编译通过；该选项未进行数值仿真。历史实际运行 harness 单独保存，不能把其通过转移给未运行分支。

这只是 prepared-input 的 phase1 单元证据。输入和前序 receipt 是明确的合成测试前提，不是权重、producer、state-transfer 或整块已执行的证明。共享仲裁、停顿/错误路径、其他 head、exp、derived、matrix、solve、state 更新、完整 Host 和最终 RTL 均未覆盖。本轮没有有效整块 MAC 利用率结果。

## 复现与后续

只交源码、生成器、依赖 pin、哈希和小型结果摘要。生成的 Fixture.scala、JAR、class、FIRRTL、权重、NPZ、原始数值数组与日志不进入 Git 或恢复包。复现使用本地已核 Maven JAR；无须下载即可完成本次实际运行。

下一步在新的有界运行中仅选择尚未完成的 guarded runtime32 两个 chunk，不重跑已完成 legacy 两例。通过后再沿原 phase2–4 的 exp/derived 数值链推进；不以这些单元结果冒充完整块。原 PID 40532 状态仍为 EXIT_UNKNOWN，本轮未重启、未释放其保留。当前空间足够，未清理任何唯一输入或证据。
