# Qwen3.5-0.8B 第 0 层完整 GDN block 的生产接线

精确提交 `d7ce9bd74a929037e459b3300134bd9f1722916e` 已完成第 0 层完整 GDN 的两次连续 M1 生产 RTL 数值验收：cold token19→carried token92，在同一 HostBlockTop 内从 raw hidden 经整层到最终残差与双状态 Fence；固定算术逐位和原官方门限共同通过。独立显式 workflow acceptance 和整个原 CI run 也已成功，见下方本次 CI 记录。M128、完整 block 的 fault/reset/restore、后继层及 35B 尚未完成。

本文保留最初接线、局部门禁和失败记录；其中历史 PENDING 仅表示当时证据边界，后续结果以精确提交和 CI 记录区分。既有 v1、v2、core-only 和旧 Qwen2 作业继续绑定其原始提交，不以本次源码重新解释旧证据。

## 生产递推写回故障与修复边界

2026-10-09 的精确提交 `904dccf2830d8caa50501041ca4895995ac41ad8` 实际 core CI 在 cold 的 pc5（第 6 条命令）返回 Memory=3。最后成功的物理 ACK 对应 head0、row127、column16 的 FP32 state；随后输出高半 32B mask `ffffffff00000000` 被真实 retained iDMA 的低位连续 prefix 契约拒绝。原独立 owner 测试直接接受该 mask，遗漏了生产接口限制。原失败日志、输入与源码身份保留，不能改写为数值通过。

本次修复把相邻两组 16 个 BF16 输出保留并合并为完整 64B，只有两组 FP32 state 全部 ACK 后才发送输出；原 FP32 算术、状态精度、顺序及官方门限不变。合法 valueDim 必须含完整两 tile，奇数 tile 几何仍拒绝。独立 owner 与生产日志审计同时限制完整 mask，并检查最后一对、第二 tile 错误、配对中 reset 和最终 ACK 屏障。修复后独立 owner 的 3 项协议/尾 pair 测试和两实际 head×128² cold→carried 均通过，每次 131584B 全 ACK，固定算术全位一致。真实 pinned iDMA 在 streaming 配置和 shared hub 两种结构中分别 31/31 通过，明确复现旧 high32 零 AXI 拒绝、完整 pair 0/31/63、最终 B 延迟 40 周期及错误屏障；这新增的是普通 MemoryRequest store 契约验证。生产 adapter 没有改变。该修复发布时，新生产整链 CI 尚为 PENDING；下方新增 d7ce 完整 block 数值结果不改写原失败。

## 实际命令链

每个 token 使用 17 条标准 Command128、216 条公开描述符记录、16 次 owner 执行和一次终端 Fence：

1. BF16 input RMSNorm，直接读取固定 embedding 的 raw hidden。
2. 三条 Dense 分别计算 QKV6144、Z2048、AB32；AB 由两份原始 A/B 权重按 K 主序合并。
3. Conv4/SiLU、Q/K L2 与 g/beta 准备、FP32 recurrent、gated RMSNorm。
4. O projection，原 raw hidden 加 O 的第一残差。
5. post RMSNorm、gate/up 两条 Dense、SiLU×up、down projection、第二残差。
6. 最后残差写 ACK 后的 Fence，同时提交真实 history/state 两个 root 和 generation。

运行目标是 cold token19 后接 carried token92，两次 M1 launch 使用同一 DUT，期间不 reset、不重新初始化 DDR。carry 的两个状态域只能读取前次实际 ACK 的写回。所有中间区预填哨兵；只预装原始 hidden、原始权重、常数和初始状态。总有用 Dense MAC 为 43,057,152，总有效写 ACK 为 2,388,096 字节；AB 参考按 256 列零填充，独立整数/C 参考为 138 个任务、43,515,904 次 FMA，不能把参考填充计为真实有用 MAC。

公开 GDN_POLICY v3 使用显式角色字段区分七条 Dense、两次 RMSNorm 和三次 elementwise。v1/v2 不借用该字段，未知组合在 owner/DMA 前拒绝。内部 kind11 对应 typed RMSNorm，kind13 对应 typed elementwise；四位 kind 不截断成旧三位值。十三组参数与已提交的双状态上下文绑定，carry 不能更换或覆盖；每条命令还核验实际生产者、物理地址、dtype、维度、步幅、权限和前驱事件。

## 资源与算术

生产路径复用原 HostBlockTop、StreamingDenseOwner、一个 MatrixPipelineService 的八个 Matrix512 切片、单一 iDMA 和共享 BlockScalarFloat。新 Norm/elementwise owner 只有存储、控制与外置 Scalar 接口，不实例化另一套算术。

input/post RMSNorm 按原模型的零中心 gamma 规则计算 FP32 `1+weight`；gated RMSNorm 继续使用原始 FP32 norm.weight，不能套用 `1+weight`。两次普通 Norm 的 BF16 输入在 FP32 中求平方、均值、epsilon 和归一化，终端一次 BF16 RNE。MLP 的 SiLU 输出必须先 BF16 RNE，再乘 BF16 up 并最终 BF16 RNE。O 的 K=2048、down 的 K=3584 均保持连续 FP32 FMA 累加，只有末端转 BF16，不能拆 K 后提前舍入。

独立 Norm owner 的真实宽度 1024 覆盖 input/post × cold/carried，共 4096 输出，固定算术和官方数据均零位差；另核验 20496 次共享 Scalar 请求/结果。独立 elementwise 覆盖两次 residual 和 SiLU×up × cold/carried，共 11264 输出，固定算术和官方数据均零位差；小协议用例另核验 701 次 Scalar 运算及尾 mask、背压、错误与共同 reset。这些结果只对应独立 owner，不替代生产整链数值。

共享 exp 的既有受限域保持显式拒绝；合法负 gate≤-80 当前由新 SiLU×up owner 返回 Unsupported，不静默变为零。Conv 和 gated norm 的既有域处理不改。FP32 state 始终保留 FP32；合法乘法 underflow/inexact 经已验证的 MulIeeeRne 返回 IEEE 舍入结果，invalid/overflow 等错误仍拒绝。正负零位差和数值 ULP 必须分别报告。

## 双重数值门禁与可靠运行

固定模型 revision 为 `2fc06364715b967f1860aea9cf38778875588b17`，Transformers revision 为 `14e738b5d0cc69aa27a95dde272aea41fde44f2f`。参考从相同原始输入、14 份原始精度参数独立计算每一实际阶段；原官方层使用自己的 cold/carried cache。每次执行都记录实际输入哈希和运行环境，不宣称跨主机官方前缀位精确复现。

硬件必须逐位等于冻结算术及状态参考，同时保留 `spec/numerical_contract.md` 的原门限：BF16 整 block 最终输出 max_abs≤0.05、mean_abs≤0.01，各隐藏运算 max_abs≤0.03125、mean_abs≤0.005。原 FP32 state 比较保持 atol=rtol=1e-4。既有 Dense/Conv 及同输入 Conv/SiLU≤1 BF16 ULP 门禁继续执行。官方门禁失败时保留固定算术的真实结果和失败数值，但总体验收失败，不用 canonical 相等覆盖 native FAIL，也不修改门限。

最初接线阶段，两 token 的完整 CPU 参考在 153.4 秒完成，138 片所有逐 K 位/flag 比较一致，39 份参考源与工具身份前后保持。cold 最终输出 max_abs=0.0001220703125、mean_abs=1.4901161193847656e-7，carried 最终输出零位差；FP32 state 的最大绝对误差分别为 1.7881393432617188e-7 和 1.1920928955078125e-7，原逐元素阈值下均无失败。全部 BF16 隐藏节点通过原 operator 门限，最大误差来自 carried QKV 的 0.0078125；同输入 Conv/SiLU 均为 0 数值 ULP。这仅说明本次真实两 token 的完整参考通过原门限，尚无生产 RTL 输出，不能关闭历史其他范围的 native 失败。

预计超过十分钟的构建和生产数值均交 GitHub 持久 CI：一次构建交接精确哈希的 ELF、RTL 与源码/工具回执，后续一个连续进程完成两 token 的 34 条命令。物理测试内存只以真实地址索引，每条命令检查已完成输出和所有未写字节；独立审计逐 strobe/ACK、所有完成快照、最终整片 DDR 及两域 carried 读取。Git 和紧凑数值工件不保存权重、NPZ 或原始 tensor；构建交接仅包含运行所必需的程序、RTL 和身份回执。

本地主源码编译通过后，完整 Host 的有界 RTL emission 在 56 秒收到 SIGKILL，exit -9，未生成 RTL。外部资源 guard 未触发，采样最低 MemAvailable 约 1.29GiB；没有足够证据指定 OOM 或其他原因。该失败及完整源/资源回执保留，未作本地重试，后续完整生成和构建交持久 CI。它不是数值失败，也不能算生成成功。

最初接线阶段尚未完成生产整链数值终态。当前仍未完成完整 block 的实际 fault/reset/checkpoint restore、M128、后继层及 35B。控制错误测试和独立 owner 的 reset 不能替代完整生产链恢复。U00.2 保持 ongoing，U01 为 to do，C02.2 原 native 门禁保持 OPEN；C03.2/C04.2/C05 只增加本次有界接线证据。

## d7ce 的完整生产数值 CI：两次连续 M1

[原 run 37900097687](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/37900097687) 的 [numerical job 113731529569](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/37900097687/job/113731529569) 于 2026-10-09 12:47:59 UTC 成功。此结果只绑定 `d7ce9bd74a929037e459b3300134bd9f1722916e`；后续 main 的新增 Attention 接线不能继承为同一数值证明。显式 acceptance job 113826113688 于 13:27:09 UTC 完成，整个原 run 也为 SUCCESS；它检查同一精确提交的 build 与数值 job 均成功。数值终态与 workflow 总验收分别记录。

两次 launch 各 17 条命令、216 条描述符；每次全 DDR 检查 46,887,680B、有效写 ACK 1,194,048B（18,657 个完整 64B beat）。同一 DUT 中间没有 reset 或重新装载 DDR。第二 token 的 Conv 从首 token 的真实已写 history 读取 768 beats，递推从真实 FP32 state 读取 16,384 beats；两次最终残差 ACK 和 Fence 后 generation 依次为 0→1→2。中间区初始化为哨兵，expected/native 数组不属于可预装区，只有真实 strobed DUT 写及成功 ACK 改变物理内存。

所有实际中间结果、history、FP32 state 和最终输出均与冻结 canonical 位精确。原官方层使用原始 14 份混合 BF16/FP32 参数和自己的独立 cold/carried cache，DUT 状态不注入 native 参考；生产 ABI 将合并 A/B 对应为 13 组参数地址绑定。native 门限保持不变：

| 项目 | 原门限 | cold token19 | carried token92 |
|---|---|---|---|
| BF16 隐藏运算 | max_abs≤0.03125、mean_abs≤0.005 | 全部通过 | 全部通过 |
| 最终 residual2 | max_abs≤0.05、mean_abs≤0.01 | 对官方零位差 | 对官方零位差 |
| FP32 state | 每元素误差≤1e-4+1e-4×abs(native) | 零超限；max_abs=1.7881393433e-7 | 零超限；max_abs=1.9572617020e-6 |
| FP32 state 原始位差 | 独立列出，不替代数值门限 | 132002 | 161534 |
| 同 canonical 输入 Conv/SiLU | ≤1 BF16 数值 ULP | 均为 0 ULP | 均为 0 ULP |

本次 native FP32 state 不能称位精确；正负零与原始位差也不能用数值 ULP 隐去。packed FP32 input preparation 的独立官方 stage 门限仍未分配，保留诊断值：两次 max_abs 为 9.5367431641e-7 和 3.3182092011e-5。它的 canonical 位精确及整层原 native 门限通过不能自动设定新的 stage 门限。第 3 层历史 full-native FAIL 保持原结论。

紧凑证据在 [独立 CI 摘要](../reports/execution/U00_2_HOST_GDN_BLOCK_CI_D7CE_20261009/result.json)。[原工件 11617056788](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/37900097687/artifacts/11617056788) 的 ZIP SHA256 为 `e07741127d89dbe44d6b2cc5e4d22b904cfa457ef05b94caa848dd1b05a61e8c`。独立复核完成 359 项检查，逐项核对 491 个精确提交源码哈希和 104 项输入/比较器/ABI 哈希，核对已验证的 ELF、RTL、构建包及两次输出身份；原 validator 的已导出字段和原门限复核通过。未导出的 layout 不补造。原始 DDR、逐 ACK 日志和 tensor 数值只在 CI 内全量验证，紧凑工件不含这些原始数据，未在本地重新数值回放。

整个 case 为 16,422.8152456 秒，包含参考、准入和审计；fresh reference 为 240.234389595 秒。未导出独立 DUT 耗时或实际完成 cycle，因此不能相减后当作仿真速度，也不能直接外推 M128 预算。当前结果是两次 M1，不是 M128 prefill；carried 多 token 的 chunk 语义和真实批次实现仍需接入与测量。完整 block 的 fault/reset/checkpoint restore、全网、35B、DC/PPA 和跨主机位精确复现继续未建立。

## 695981 与 675d 的后续精确提交验收

以下两条原 CI 均已独立完成完整第 0 层 GDN 的 cold token19→carried token92 数值验收，并通过各自显式 acceptance。它们分别绑定 `6959810545203d5f9508075b311dba52f1bee0c9` 和 `675d0ccfb3a189bcd18fede0fda6cc78fee6a282`；上文 d7ce 的首次通过记录保持不变。

| 精确提交 | 原数值 job / UTC 终态 | 显式 acceptance / UTC 终态 | 独立检查 / 精确源码哈希 | 整个 case 秒数 |
|---|---|---|---|---|
| 6959810545203d5f9508075b311dba52f1bee0c9 | [113821750506](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/37924374860/job/113821750506)，18:06:48 SUCCESS | [113957310366](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/37924374860/job/113957310366)，18:06:55 SUCCESS | 1644 / 528 | 16951.509792187 |
| 675d0ccfb3a189bcd18fede0fda6cc78fee6a282 | [113834908181](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/37928256911/job/113834908181)，18:02:28 SUCCESS | [113955587512](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/37928256911/job/113955587512)，18:02:37 SUCCESS | 1666 / 544 | 16416.734598095 |

表内日期均为 2026-10-09。两个 run 的 build、数值和 acceptance 三个 job 均绑定本行精确提交；acceptance 只在本 run 的 build 与 `block-canonical-native-pass` 均成功后通过。两份独立审查分别核对 GitHub ZIP digest、可信构建输出给出的包哈希、全部 15 个构建包成员及实际 ELF/RTL 字节，按流式读取核验，没有执行或展开这些大文件。原 build 源码清单分别为 504 和 520 项，均包含于各自精确源码闭包；编译入口 wrapper 与实际 compiler ELF 的身份分开记录。每份数值证据的 104 项输入哈希清单、43 条原始 tensor 获取记录及固定模型来源均核对；只对可重建的五份 ABI 和初始零状态重新计算字节哈希，不声称本地重算全部数值输入。

每个提交都实际完成两次 M1，每次 17 条命令、216 条描述符、1,194,048B 写 ACK、18,657 个物理 64B 写 beat，以及 46,887,680B 全 DDR 检查。第二次 launch 在同一 DUT 内读取前一次成功 ACK 的 768 个 history beat 和 16,384 个 FP32 state beat。总有用 Dense MAC 为 43,057,152；独立参考填充后的 FMA 为 43,515,904。两次 M1 不能称为 M128 prefill。

两份新证据分别观察到相同的下列指标，但不据此宣称跨主机输入、工具或 RTL 字节等价：canonical 中间节点、双状态及最终输出均零位差；两 token 的原 native `residual2` 均零位差，max/mean error 均为 0。FP32 state 原始位差为 132002 / 161534，原逐元素容差失败为 0 / 0，最大绝对误差分别为 1.7881393432617188e-7 / 1.9572617020457983e-6。state 的数值门通过不改称原始位精确。PREP 的位差为 2176 / 2606，最大绝对误差为 9.5367431640625e-7 / 3.3182092010974884e-5，仍是未分配门限的诊断项。

原门限全部保持：BF16 隐藏运算 max_abs≤0.03125、mean_abs≤0.005；最终 residual2 max_abs≤0.05、mean_abs≤0.01；FP32 state atol=rtol=1e-4；同 canonical 输入 Conv/SiLU≤1 BF16 数值 ULP，本次均观察到 0 ULP。正负零数值相等与原始位差分开保留。上表耗时包含参考、准入、执行及审计，没有单独导出的 DUT 秒数或完成 cycle，不能作为纯 RTL 吞吐，也不能把不同提交或机器之间的差值归因为 `-O2` 提速。

紧凑结果见 [后续两提交验收摘要](../reports/execution/U00_2_HOST_GDN_BLOCK_CI_FOLLOWUP_20261009/result.json)，其中记录独立 receipt、ELF、RTL、输入/输出身份、ZIP 和构建包哈希，以及各原 run/job/artifact 链接。695 的[数值工件 11634704403](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/37924374860/artifacts/11634704403) ZIP SHA256 为 `7fbd7a18cffd70f547eb6030c6a9cfeabfc0562486d011726c808663e679c851`；675 的[数值工件 11636065241](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/37928256911/artifacts/11636065241) 为 `f95e68821cebf7db0941105a9bac10b1049a715566f687c798bce893d4a1c809`。摘要只保存计数、哈希、指标、门限和来源链接，不复制权重或原始 payload。

这两份独立回执在本地环境状态回退后，依据当前可读的精确 Git 对象、CI 工件和 job 元数据/日志重新建立；没有据旧路径声称此前未提交的 work 文件仍存在。原始 tensor、完整逐 ACK 事件和 DDR 快照未上传，本地没有重新数值回放。原 immutable 包 validator 完整复核，数值 validator 只重验已导出字段；没有补造未导出的 live session、原始数组或完整 layout。

两个提交各自 core-only 超时，以及相应 Attention / QKV-Norm-RoPE 范围的历史失败保持原结论，具体原 run 列于摘要；第 3 层历史 full-native FAIL 也不被本次第 0 层结果覆盖。完整 block 的 fault/reset/checkpoint restore、M128、后继层、全网、35B 和 DC/PPA 继续未建立。本次仅追加精确提交证据，不改变全局 checklist 的状态。
