# Attention 完整顶层函数采样：VL_CONCAT_WWI 聚合热点

本次已取得实际函数级采样：在 4096 cycle prefix 的 **8438 个 `eval()` 调用线程 self-CPU 样本**中，`VL_CONCAT_WWI` 的 constprop/isra clone 占 **6422 个，76.1081%**，是占比最高的聚合 helper。该结果尚未确定 helper 的调用者、相关位宽来源或 RTL 模块。未知样本 **1016 个，占 12.0408%**，必须保留为未知。

[run 37982064254](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/37982064254) 的 [job 113994781438](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/37982064254/job/113994781438) 于 **2026-10-09 20:38:44 UTC** 成功，表示有界诊断完成。完整命令链和数值验收没有完成，也没有提速或物理 QoR 结论。可提交结果见 [紧凑摘要](../reports/execution/U00_2_HOST_ATTENTION_HOTSPOT_331AA938_20261009/summary.json)。

## 对象与采样范围

生产源仍固定为 `6959810545203d5f9508075b311dba52f1bee0c9`；本次诊断提交为 `331aa938eb820ac15deb13a7bbc927373d5b7924`。实际采样对象是冻结 `EmitHostBf16AttentionCore` 配置的完整 `HostBlockTop`。本次不增加 GQA 仿真边界，不改变功能 RTL；该完整顶层仍不是完整 Attention block 的数值验收。

构建一次，在同一 ELF、同一新生成 fixture 上顺序运行采样关闭、开启的两个 prefix。两个 prefix 各 4096 cycle、12288 次 `eval()`，确定性字段、事件和原 stdout 哈希严格一致，终态均为 `run=0`、`pc=0`、完成命令数 0。两次的 pipeline issue/AR handshake 都为 80，R handshake 为 794。功能 SV SHA256 均为 `4f061c48397979339ff97bef5a5e9f9dee2bd4a0dec7a5637f8a95b5de2e45f9`；ELF SHA256 为 `0c9ccbf8bddbae084b8e2299a886c819684d8d6dfc8092ebe8a2dc1411ed3c1e`。

采样以 `CLOCK_THREAD_CPUTIME_ID`、定向 `SIGEV_THREAD_ID` 和 `SIGPROF/ucontext RIP` 实现，间隔为 9,973,000 ns。开始和结束均观察到 **4 个线程**，但只采集 `eval()` 调用线程，其他 helper/worker 线程的 CPU 时间不在范围内。三个 eval phase 的样本数依次为 1663、3520、3255；13 次窗口外事件不计入 8438 个有效样本。缓冲容量 65536，未饱和，buffer drop 和 timer overrun 均为 0。周期采样及信号投递仍可能产生偏差。

## 已解析热点与未知项

| 已解析函数（按 self 样本数） | 样本 | 占全部有效样本 |
| --- | ---: | ---: |
| `VL_CONCAT_WWI`，constprop/isra clone | 6422 | 76.1081% |
| `VHostBlockTop___024root___nba_comb__TOP__282` | 205 | 2.4295% |
| `VHostBlockTop___024root___ico_comb__TOP__227` | 132 | 1.5644% |

第二、第三项分别映射至生成文件 `obj/VHostBlockTop___024root__DepSet_h74254c49__94.cpp:568` 和 `obj/VHostBlockTop___024root__DepSet_h74254c49__13.cpp:787`，身份哈希保存在紧凑摘要。这只是这些函数自己的样本及定义位置，不能把它们当作领先 helper 的已证调用者。

主 ELF 共 7408 个样本，其中解析 7393、未知 15；`libc.so.6` 共 1030 个样本，其中解析 29、未知 1001。两者的未知合计 1016 个。当前没有证据把这些 libc 未知样本指认为 `memcpy` 或其他实现。

领先 helper 没有生成源码映射，未取得调用栈、调试行或内联 frame 归属，因此目前只能定位 helper 聚合热点。不能据其函数名或样本比例直接指认某个 RTL owner、网络、位宽或物理硬件瓶颈，也不能据此声称硬件 MAC 利用率。

## 计时、输入变化与数值边界

本次构建耗时 **2783.121230576 秒**；采样关闭、开启的 `eval()` 累计分别为 **84.941082435 秒**和 **84.109330578 秒**，对应完整插桩 step 为 85.126943725 秒和 84.297778978 秒。总实验耗时 3154.874218561 秒，原预算和各阶段上限均遵守，supervisor 正常退出。开启采样时的计时包含窗口管理和信号 handler；一次 off/on 顺序测量的差值不能当作提速，也不能精确估算采样器开销。

官方 baseline/AVX2 本次各 fresh 执行一次，没有复用旧执行。同一次 run 内两个 prefix 的 fixture 不变，但**本次 activation 与前次 A/B 不同**：

- 本次：`ff5b88559102bf22e9808d7a9939f7fe0376d32403db9fbb4450e198e3978d23`
- 前次 A/B：`f8ae9b179fb3a322c64a623329a27d3912b563aad3d0a23249a6789d65e4c7d0`

另外六项输入哈希相同。不能把两个 run 描述为相同输入复测，也不能比较两次 run 的计时后宣称提速。前次 [GQA 边界 A/B 负结果](U00_2_HOST_ATTENTION_PROFILE_AB_8A937EAD_20261009_CN.md) 继续独立绑定其原输入和提交。

本次原 native full-block 门禁仍失败：**baseline 11 项、AVX2 13 项比较失败**。这不是前次 A/B 的 6/5 项结果，不能混用或据此作同输入的改善/回退判断。[既有 GDN 完整双 M1 PASS](U00_2_HOST_GDN_BLOCK_20261009_CN.md) 与 [Attention full block 未完成状态](U00_2_HOST_ATTENTION_BLOCK_20261009_CN.md) 保持原证据边界，不因本次采样改变。

## 核验与证据保存

独立复核完成 619 项生产源和 13 项诊断源 Git blob 哈希核对，并重建九项插桩文件；没有发现源码身份不匹配。17 条已记录 C++ 编译命令实际生效优化均为 `-O2`，全部保留 `-ffp-contract=off` 和 `-fno-fast-math`，没有实效 `-O0` 证据。原功能 SV 在 Verilation 与 C++ 编译前校验。runner 在两 prefix 前后绑定构建、源码、输入与 ELF，采样及符号分析也绑定同一 ELF。

[原工件 11643857799](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/37982064254/artifacts/11643857799) ZIP 为 54265 字节，SHA256 为 `611472266e2e02c7c0a7de2dfd43d2be474174a642cb010bf0d75d6745dbdd93`，仅含原 `summary.json` 与 `source_input_hashes.json`，成员字节与保存文件一致。独立复核回执 SHA256 为 `2bfc0819a6c254ad913b900750fcbbe88d23d0b74fae9f15a6abd4276ab5e45f`。四份本地证据位于 `work/attention_hotspot_ci_331aa938/`，各文件大小和哈希保存在紧凑摘要。

原工件未上传原始采样、ELF、RTL、生成 C++ 或 fixture 字节。独立复核检查导出回执的身份绑定及源码算法，未在本地重新符号化，也未对不可用原始文件重算哈希。提交材料仅为本文与紧凑摘要，不提交 ZIP、模型数据、权重、NPZ、原始 trace 或巨大 mangled 符号。

## 下一步：仅生成代码检查调用方与位宽

下一步限定为 **codegen-only**：先核对原 SV 身份，再执行层次 Verilation，生成 C++ 后、C++ 编译前停止。检查 `VL_CONCAT_WWI` 的实际调用位置、调用函数与参数位宽，报告静态调用点及证据哈希；静态调用点数量不等于各调用点的运行时间贡献。

此步骤不执行官方模型采集、fixture/数值运行或新一轮完整 A/B。本次采样尚未提供这些调用方与位宽结论；后续结果须另行绑定其确切源码、SV 和生成工件身份，不能在本文中提前指认。
