# 已闭 P0 首 fault：有限控制证据与 n0 局部比较

本包仅有限 JSON 与说明；不含本机路径、原日志、输入权重、张量载荷或 DUT 输出二进制。`SAFE_EVIDENCE.json` 绑定真实 manifest `7a99c2c8…`、ELF `b89a701b…`、SV `3d148277…`，builder `3c38f048…` 与 executor `1a50c6d9…` 分开记录。全部身份及 receipt 完整 SHA 在 JSON 中。

## 实际终态

9 项前置阶段 native 0 并严格收尾；P0 DUT 子进程 exit 1，外层 consumer / controller transport exit 2。DUT 外层原回执 errors[]、cleanup 完整、EOF/gzip 完整，6036.662749 秒，采样 RSS 248,307,712 B。RSS 是监督采样，不是完整峰值保证。

原 watchdog 为 10800 秒 / 1,500,000 active cycles，终止原因为 `RESET_REQUIRED`，不是 watchdog 超时。P0 状态仍 `STARTED_NATIVE_FAILED / INCOMPLETE`，P1–P4 为 `NOT_SELECTED`，不是四项失败或通过。全块数值、生产验收、最终 RTL 验收均 false；没有完整利用率分母。

## 两槽固定控制快照

原 schema SHA `75088081cf6c3425eba9af3b44c78244f8c62697b4390f992ad63e21f16c7de4`，114 个控制信号，上一健康槽与当前故障槽各保留完整有序数值。JSON 附 index / symbol_key / width / validity，解释必须同时遵守原 schema 的有效性限定，不能把未有效或 raw-only bits 当完成事件。缺失信号明确列为未观测，不补零；没有额外 eval/clock，也没有数据载荷或地址。

- 上一健康槽 cycle 852611 / active 852606；故障槽 cycle 852612 / active 852607；两者 completions=1。
- 故障槽 owner 的 window/done status 原始字段为 8，原 Status 枚举解码为 Numerical；该两字段是 RAW_ONLY_NO_COMPLETION_CLAIM，不能据此声称一次合法退休事件。
- 同槽 Guard ownedAuthorityFault=1，而 localFault、faultNow、unknownReply、wrongReply 等所列独立异常位为 0；Top physicalFault=1、ordinaryAdmissionFault=1、numericalFault=0。这里只记录故障反射，不能把 Guard 或 physicalFault 标签认定为唯一首因。
- 同槽所列 Matrix outputBad、endpointError、completionBad、anyLeafFault、idleUnexpected、lifetimeQuarantine 均为 0。只表明这些已观测协议错误位未置位，不证明整个 Matrix 或数值路径无错。

同拍 snapshot `wideSteps=12800`；最后一次周期性 HOST_PROGRESS 的 `pipeline_issues=12739` 来自更早 cycle 852549 / active 852544。两者采样时点不同，不混为同拍计数或当作矛盾。最终 sample 的 useful_macs/executed_macs=0 亦不构造完整效率结论。

## n0 已写完输出的独立局部结果

原 pc0 的 n0 在 cycle607643 已写完 786432 B。仅这一输出的形状 [1,128,1536]、196608 words，经实际比较及独审，逐 bit 等于官方独立 BF16 参考的 uint16 左移16位存储扩展，无重新舍入。actual 与 expected-layout SHA 均 `ddee5fd75094777c51ef1104c7a18dfe527fef9de2a24646aad1d83160a6e421`，word/byte mismatch=0、低16位非零=0、双方 nonfinite=0。

本地比较 summary `9a7472af…` 与独立核验 receipt 均已绑定。比较使用原 consumer 的精确比较语义；未重跑 DUT、未重新计算参考，未因此重哈希 ELF。本结果只覆盖已写完的 n0 最终输出，不覆盖全部内部中间值、随后 pc1 的故障点、完整 P0 或其余四块。首故障根因仍未唯一确立，后续须按实际控制与算术证据继续定位，不迁移局部匹配为 whole-block PASS。

采集器没有具体返回数据 word；故障 lane、NaN/Inf 实际值以及 padding 是否相关均未知。后续源码静态条件推论应另列来源，不改变本快照的 fault_cause_established=false。

## 源码不变量推导（不是新增直接采样）

另有已独审 `STATIC_EXCLUSION.zh.md`，SHA `b8546e489c04c8ed6c220677f478aa7b7a959f501ff0e05964ebfd871bb27066`。在报告所列实际窗口身份与已 pin Scala 可达性前提下：previous 槽 result.ready=1 排除会无条件强制 ready=0 的 drain 分支；terminal 最后 half 的已完成加载以及无 outstanding / 后续 prefetch 的源码约束排除 DDR sourceFinite 写状态路径。结合 status8 的首次锁存和其余 Numerical 写入口的排除，推导定位到 previous 槽 context0 result.fire 的 finite 检查失败。该定位依赖源码不变量，不是快照直接记录了 finite 位或返回数据。

该 K-window 为 FP32，无 BF16 物化阈值项；M128 条件使检查覆盖整个 16×256＝4096 个返回词，而不是仅保证逻辑有效输出的某个子集。具体坏字、NaN/Inf 类别、有效/无效物理 lane、padding 作用及更上游算法/存储根因仍未知。SAFE 仍只记录原直接观察，`fault_cause_established=false` 不改，不能据此宣布唯一最终根因。
