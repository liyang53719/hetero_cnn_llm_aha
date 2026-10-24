# Qwen3.5-0.8B 第0层 cold128→carried128 完整软件块验收

状态：**PASS，严格限于本次固定输入、固定策略的 typed-software L0 完整块及原已分配数值门限。** 不是全部模型层、全部输入、Torch bitexact、Scala/RTL 或硬件性能验收。

## 已完成

- 源码固定在 `1ea9b511fc982b2d928472b0dadd9f794c1c20d8`，tree `e6af2af0b35b7c12907a1ff0b66dd416f0e90571`。
- 实际执行先 cold128，再用其实际提交的 history/FP32 state 执行 carried128；自然 exit 0，32 个成功终态、2 次联合提交、最终 generation 2、38 份张量清单。没有注入下游 golden，没有重跑实际计算。
- 两个窗口各 17 项已分配节点/状态门限和 7 项重叠 operator 门限通过。总计 48 次 gate evaluation 不是 48 个独立边界；QKV/Z/AB/Conv-SiLU 等有重叠。
- 最终 cold128 输出 max/mean absolute error 为 `0.001953125 / 5.045527416314144e-6`；carried128 为 `0.0009765625 / 5.384688847698271e-6`，均在原 `0.05 / 0.01` 门限内。两个窗口 FP32 state 的原逐元素 `atol=rtol=1e-4` 门限违反数均为 0。
- Prep 及其组件保留 `passed=null / thresholds=null`，不计作通过。完整 compact 数值表见同批 `summary.json`。
- 独立终审复核 3838 项新旧 plan pins、93 个参考文件及 23583 项 runtime 记录，并核查原时钟、清理证明、原失败保留。终审只读复核已有结果和证据，不另行计算数值。

## 原失败和修正归属

第一次 comparison 在数值计算前发生 import/setup FAIL，原因是 109 文件的选定比较源码根缺少 `qk_norm256_candidate.py` 及其依赖 `rope_bf16_candidate.py`。该次 exit 1 和 cleanup 证明保留。

修正仅建立同一 Git commit 的 111 文件独立比较源码副本：原 109 文件逐字一致，增加上述两份原仓库源码；没有修改已结束的 actual 源码根、实际输出、原 PLAN 或原 workflow clock。经独立审查的 corrected comparison exit 0、cleanup 确认，随后在原截止时间内完成最终 pin 校验。

原始 actual receipt 的 `ACTUAL_COMPLETE_UNCOMPARED`、`native_acceptance=false` 不改写。数值结论独立归属于 `PASS_CORRECTED_POSTFLIGHT_NUMERICAL_COMPARISON` 和最终 `numerical_acceptance=true`。没有 reference recapture，也不推断旧 UNKNOWN run 的结果。

## 本批公开材料与验证范围

- `reports/execution/QWEN35_FULL_M128_COLD_CARRIED_20261024/summary.json`：仅白名单有限标量、紧凑指标、原阈值、状态和证据摘要哈希；不上传 9 MB 原始比较报告。
- `SOURCE_PINS.json`：111 个已公开源码/既有 tensor-header metadata 的大小、SHA-256、Git blob identity；不包含权重、张量值或新上传的二进制。
- `REPRODUCE.md`：原 payload/fixture/native capture/full_driver/full_compare 入口、版本、参数和资源约束。输入、权重、参考与 native 库只在本地按需准备。
- `verify_sources.py` 与测试：仅 stdlib，实际核验 111 份选定文件；16 个 synthetic integrity 测试 normal/-O 各通过。该 PASS 不代表实际模型重跑，也不检查完整仓库、Git HEAD 或 native/runtime 资格。
- 公开 recipe 不打包私有 bounded supervisor 及机器相关配置，不宣称一条命令即可复现当时监督流程；重新配置路径须形成新的 freeze/hash，不可复用历史 PLAN digest。

## 边界与后续清单

- [x] 两个 M128 窗口的既定软件数值门限、actual/native cache continuity 和 final pins 完成。
- [x] 保留原 import FAIL、旧 UNKNOWN、既有原始 receipt，不伪造连续成功历史。
- [x] 源码、复现入口、验证脚本与中文范围说明小批公开，数据留在本地。
- [ ] RTL/硬件执行、当前 Scala 映射对应性及硬件周期/MAC 利用率仍未建立；这些字段为 false/null。
- [ ] 不从 allocation guard 的 host 微测推导本次端到端加速或硬件收益；本批无性能声明。

后续工作继续按用户既有维护授权执行。任何新的运行单独冻结输入、资源预算和验收计划，不改写本次已终止运行的预算或历史证据。
