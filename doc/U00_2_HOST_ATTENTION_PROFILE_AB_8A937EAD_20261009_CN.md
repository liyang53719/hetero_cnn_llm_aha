# Attention 完整顶层 GQA 仿真边界 A/B：负结果与后续采样

本次 **不采用 GQA 边界候选**。同一 runner 上先基线、后候选，各执行两个 4096 cycle prefix；候选两次 `eval()` 实测均慢于基线两次，均值由 **87.1451434 秒增至 148.8331068465 秒，增加 70.79%**。构建时间由 **3016.149331275 秒增至 3117.476007985 秒，增加 3.36%**。这是本次有界仿真配置的负结果，不能外推为具体模块瓶颈或硬件性能结论。

[run 37958175705](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/37958175705) 的 [job 113913923585](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/37958175705/job/113913923585) 为 SUCCESS，含义仅为实验完成。四个 prefix 均未完成首条命令，完整命令链、数值验收与提速均未建立。可提交的 [紧凑摘要](../reports/execution/U00_2_HOST_ATTENTION_PROFILE_AB_8A937EAD_20261009/summary.json) 保存结论、计时、身份哈希及证据链接。

## 冻结范围与可比性

- 生产源固定为 `6959810545203d5f9508075b311dba52f1bee0c9`；诊断与触发提交为 `8a937eadccf4e33f75ee11b7971ebdaa5236da94`。
- 实际对象是冻结 `EmitHostBf16AttentionCore` 生成的完整 `HostBlockTop`，包含该配置的全部顶层结构。它仍是 Attention core 配置，不是已经完成整层验收的 Attention full block。
- 两方案功能 SystemVerilog 的 SHA256 均为 `4f061c48397979339ff97bef5a5e9f9dee2bd4a0dec7a5637f8a95b5de2e45f9`，与原失败对象一致。候选只在原仿真层次配置增加一个 `Bf16CausalGqaOwner` 的 `hier_block`；新增对应仿真库构建阶段，不改变功能 RTL。
- 原生产 driver 保持逐字节一致；诊断包装器及只读计时/事件采集应用于副本。prefix 包含构造期 36 cycle，在第 4096 cycle 的第三次 `eval()` 及原 ACK/store 记账结束后停止，每个 prefix 共 12288 次 `eval()`。
- 两方案共享同一份新生成、未改变的 fixture。官方 baseline/AVX2 各 fresh 执行一次，共两次，未复用旧官方执行；七项输入身份在紧凑摘要中保留。不能据此宣称跨主机官方前缀逐位复现。
- 独立复核以对应 Git blob 核对 619 项生产源和 10 项诊断源，并重建两个构建脚本、六项插桩资产、转换回执及候选配置，未见身份不匹配。两方案的 RTL、source manifest、scope、HardFloat、compiler jars、toolchain 与实际 Verilator 身份回执一致。
- 编译回执中基线 17 条、候选 19 条 C++ 编译命令均保留 `-ffp-contract=off` 和 `-fno-fast-math`，实际生效优化均为 `-O2`。出现 `-Os -O2` 的命令以末尾 `-O2` 为准，没有实效 `-O0` 证据。

## 实测计时

| 指标（秒） | 基线 | GQA 边界候选 |
| --- | ---: | ---: |
| 构建 | 3016.149331275 | 3117.476007985 |
| prefix 0 的 `eval()` 累计 | 87.19634147 | 153.720475774 |
| prefix 1 的 `eval()` 累计 | 87.09394533 | 143.945737919 |
| 两次 `eval()` 均值 | 87.1451434 | 148.8331068465 |
| 两次完整插桩 step 均值 | 87.3578586375 | 149.066726824 |

候选/基线 `eval()` 均值比为 `1.7078760908493724`，构建比为 `1.0335947148436337`。总实验时间为 6837.378587646 秒，原总预算、构建和 prefix 限额均遵守，supervisor 正常退出。

这些是同 runner 顺序执行、每方案两次的有界观测，包含插桩开销。`eval()` 占插桩 step 时间约 99.75%–99.84%，只说明该计时范围内时间集中在仿真求值；它不定位生成函数、逻辑模块、MAC 或内存瓶颈。不同方案的函数边界会改变仿真器执行方式，本次证据不解释回退原因。

## 确定性检查及验收边界

四个 prefix 的完整确定性对象相等，报告的事件 SHA256 均为 `ac6ccca4fa5e761e9f3c1b1d957fda305091824721db62448b556d13d2380e84`，原 stdout SHA256 均为 `1a8408b275a5ef753d881cd06a0107c0a74d7d00ebcbec4b5c16e7d706f091fa`。各 prefix 都是 4096 cycle、0 个 incomplete step、1 个 issued job、80 次 pipeline issue、80 次 AR handshake、794 次 R handshake；接受 806 beat、确认 794 beat、待返回 12 beat。终态 `run=0`、`pc=0`、完成命令数为 0。

因此，确定性相等仅覆盖观察到的 prefix，不构成完整功能等价证明。原 native full-block 门禁仍是 baseline 6 项比较失败、AVX2 5 项比较失败；本实验没有更改原门限，没有获得数值 PASS。

既有 [GDN 完整双 M1 生产数值 PASS](U00_2_HOST_GDN_BLOCK_20261009_CN.md) 的 d7ce 原始结果仍只绑定 `d7ce9bd74a929037e459b3300134bd9f1722916e`；后续精确提交由该文档分项记录，本报告不重绑任何既有证据。[Attention full block 文档](U00_2_HOST_ATTENTION_BLOCK_20261009_CN.md) 所述整链数值、cold128/carried128 和恢复待办保持原状态，本次 A/B 不关闭任何关联大项。

## 证据保存与下一步

原证据保留在本地 `work/attention_profile_ab_8a937ead/`：`summary.json`、`source_input_hashes.json`、`independent_verification.json` 和 `artifact.zip`。ZIP 只含前两份 JSON，已检查其成员字节与保存文件一致。紧凑摘要记录这四个文件的大小和 SHA256；ZIP SHA256 为 `e64b27efe78ff8cd8ad1267d961181c9b3600da0189b488c499ae479791e7db9`。

本次提交材料仅为本文与紧凑摘要；不提交 ZIP、权重、NPZ、tensor、原始 trace 或生成 binary。紧凑原工件也不包含 CI 原始 RTL、ELF、事件、输入 payload 和完整编译日志，因此这些身份是回执之间的核验，未从不可用的原文件重新计算哈希。源码 Git blob 核验与原工件字节核验分别有明确依据，不能把回执核验写成重跑 DUT。

下一步是 **在相同冻结完整顶层上做函数级有界采样**，继续绑定生产源、功能 SV、输入、工具链、严格 FP 和实际 `-O2`。采样需报告实际生成函数的符号映射、观测窗口、样本覆盖和开销；保留同一确定性 prefix 检查。获得函数级证据后再选择下一候选。此处仅记录后续方向，尚未执行，也不推测热点。
