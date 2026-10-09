# Qwen3.5-0.8B GDN 生产命令链接入计划

更新时间：2026-10-09。这里的完成状态区分独立 owner、生产 Host 命令链和完整模型 block。独立 owner 通过不能关闭完整 block 门禁。

固定来源为 Qwen/Qwen3.5-0.8B revision `2fc06364715b967f1860aea9cf38778875588b17`，Transformers revision `14e738b5d0cc69aa27a95dde272aea41fde44f2f`。权重精度以 layer0 payload pin 为准；不得把 A_log、norm.weight 或 recurrent state 降为 BF16。

## 最新推进：完整层 policy v3

v2 core 已发布于 `904dccf2830d8caa50501041ca4895995ac41ad8`，其原持久 CI 继续执行。后继 v3 已接通真实 raw hidden → input RMSNorm → core → O → residual1 → post RMSNorm → gate/up → SiLU×up → down → residual2 → 双状态 Fence，共 17 命令、216 记录。两种新增 owner 的真实小 RTL、全部主源码编译分别通过；生产整链数值仍 PENDING。具体算术、公开协议、两种验收和剩余范围见 [完整 block 接线说明](../../../doc/U00_2_HOST_GDN_BLOCK_20261009_CN.md)。

新增 kind11 typed RMSNorm 和 kind13 typed elementwise 共用原 Scalar；O/FFN 复用原 Dense/Matrix。input/post Norm 使用原始 BF16 gamma 的 `1+weight`，gated norm 保留原 FP32 gamma；SiLU 必须先舍入 BF16 再乘 up。O/down 的 K=2048/3584 参考保持连续 FP32 累加，末端一次 BF16 RNE。十三组参数随最后成功双状态 Fence 保留，状态提交点已移到第二残差 ACK 之后。当前仍仅两次 M1 连续 launch；M128、整链 fault/reset/restore、后继层和 35B 尚未验收。

下列 v1/v2 阶段记录描述各自原始边界，不因 v3 源码接通自动提升为实际数值通过。

## 当前最小闭包

- 生产标准 Command128、TypedTensorReader、HostBlockTop、StreamingDenseOwner、同一 MatrixPipelineService 的 8 个 Matrix512 切片和同一 iDMA 已接入 GDN QKV 投影与 Conv4/SiLU。
- 待实际数值验收的序列为 Dense(token19) → Conv cold → Dense(token92) → Conv carried。Conv 的输入只能读取前序 Dense 已 ACK 的写回；carried history 只能读取前序 Conv 已 ACK 的 history。
- 6144 通道 Conv 的独立 owner 门禁已覆盖 cold1、carried1、cold16、carried16。208896 个输出对固定算术逐位一致；与官方同输入运算的数值 BF16 ULP 为 0，但原始位比较保留 9/9/116/116 个正负零差异。M16 组合输入用例不等于官方完整连续 block。
- 生产 Dense→Conv 源快照已构建成功。本地四命令会话中断，无退出回执、无完成命令，不计数值失败或通过；已发布 `a41749a2e774fa7c0d42be8a28806489f2ca081b`，交原 GitHub Actions 持续执行，仍待终态与独立物理 DDR 审计。输入边界目前是官方 embedding → input RMSNorm 的 BF16 输出，input RMSNorm 不在 DUT 中。
- 已发布 v1 profile 默认关闭，仅 Dense QKV 和 Conv4/SiLU。后继未发布 v2 core 接入 QKV/Z/AB、Conv、InputPrep、recurrent、gated norm 与双状态 Fence，共八命令；目前仅编译与前端控制门禁通过，实际生产数值待验。U00.2 仍在进行，U01 未开始；C02.2 官方完整精度门禁仍开放。

## 完整 GDN 的数据依赖与接入顺序

| 顺序 | 运算与实际布局 | 当前进展 | 下一最小生产修改 |
| --- | --- | --- | --- |
| 1 | input RMSNorm：H=1024，BF16 输入，FP32 累计，使用 `(1+weight)`，BF16 输出 | 官方输入边界已固定，DUT 未覆盖 | 接 typed BF16 Norm owner，输出直接作为后续 Dense A |
| 2 | QKV 投影：A[M,1024] × W[1024,6144] → BF16[M,6144] | 生产 Dense 已接，四命令数值正在验收 | 完成原真实 cold/carried 两 token 验收 |
| 3 | Conv4 + SiLU：权重/history 为 BF16[6144,4]，输出 BF16[M,6144] | 生产接口已接；独立 owner 已验 | 六个写回 span、最终 ACK、history generation 和出错不发布共同验收 |
| 4 | Z 投影 N=2048；A/B 投影各 N=16 | 未发布 v2 已接角色，数值待验 | 同一 Dense 使用 Z 和 AB32 角色；把两份原始 N16 权重按 K 主序拼为 W[1024,32]，得到一个 BF16[A0..A15,B0..B15] 64B beat，不填充预计算 gate |
| 5 | Q/K L2、Q scale、V 无损升 FP32；g/beta | 独立真实 Scalar 两头冷/暖 M1 已逐位通过，未发布 v2 已接 Host | 生产命令读取完整 Conv Tensor、AB32、A_log FP32[16]、dt_bias BF16[16]；写 Q/K/V FP32[16,128] 和每头 64B 的 g/beta 记录 |
| 6 | FP32 recurrent state[16,128,128]，terminal core BF16[16,128] | 独立两真实头 cold→carried 已验，未发布 v2 已接 Host | kind9 接同一共享 Scalar 与 memory；out-of-place state staging，core 最终 Fence 才共同发布 history/state generation，不能提前在 Conv 完成时推进可见状态 |
| 7 | gated RMSNorm：core/z BF16，FP32 方差；先舍入 BF16 norm，再乘原始 FP32 norm.weight 与 FP32 SiLU(z) | 独立 16-head 单 job 两 token 共4096值逐位通过，未发布 v2 已接 Host | kind12 的生产数值链待验；禁止套用 Attention 的 `1+weight` |
| 8 | out_proj：BF16[M,2048] × W[2048,1024] → BF16[M,1024]；残差 | 未接此 profile | 扩生产 Dense 的 K/角色，接真实 residual 输入，不注入中间参考 |
| 9 | post-attention RMSNorm、gate/up、SiLU×up、down、第二残差 | 未接此 profile | 原 0.8B H=1024、FFN=3584 的真实 typed BF16 链；完成后才验完整 block |

内部 owner kind 明确扩为 4 位；kind8 为 Conv、kind9 为 recurrent、kind10 为 InputPrep、kind12 为 gated norm。公开 policy v2 与 AUX_ROOTS 0x23 已定义；未实现的值必须拒绝，不能截断回旧的 3 位编码。

InputPrep/recurrent 初始门禁仅 M1。扩大到 M128 前必须实现真实 token/head 步进、完整 Conv Tensor 的 6144 通道行跨度、合法命令容量和 state 依赖。不得用 17-token 跨界检查或 M128 shape 准入替代 M128 数值执行。

## 共享算术与精度边界

- Conv、InputPrep、recurrent 和 gated norm 只发外置 Scalar request/result，由生产 core 的同一 BlockScalarFloat 服务处理，不能新增私有 FPU、矩阵阵列或 iDMA。
- `MulIeeeRne=6` 显式接受 IEEE RNE 的 underflow/inexact，保持 invalid/div0/overflow/nonfinite 拒绝；旧 Mul 的异常策略保持。真实 channel397 极小乘积返回负零的正确结果不应被误拒绝。
- `Softplus=7` 默认关闭，仅新 GDN profile 显式启用。复用现有 exp/ALU/divider，FP32 每步 RNE；`x<=-80` 是当前未覆盖的合法输入域，按 Numerical 拒绝且不发布。源码诊断误差不等于官方独立 stage 通过；整 block 原有门限不变。
- Q/K 的 BF16 节点、beta 的 BF16 RNE、cold chunk 乘缩放与 carried M1 除缩放分别按固定官方路径记录。独立固定算术逐位门禁与官方数值误差门禁分开报告。
- Conv history 为 BF16，recurrent state 为 FP32。两个状态域在 v2 中由终端 Fence 共同发布，前端控制门禁已覆盖；实际数值与错误恢复仍待生产验收。完整 block 必须把同一 Fence 移到 O/residual/postnorm/FFN/down/residual 全部 ACK 之后。显式 checkpoint restore 尚未实现，不能用参考重建状态替代恢复。

## 完整 block 的下一条实际链

输入边界必须从真正的 layer0 hidden 开始，先由 DUT 计算 input RMSNorm 并写 BF16，再作为三条 Dense 的唯一 A。core 之后依次接同一 Matrix 的 O projection、真实 residual、post RMSNorm、gate/up、SiLU×up、down 和第二 residual。原始 hidden 必须保留到第一 residual；两次 Norm 的 `(1+weight)` 与 gated norm 的原始 FP32 weight 分别处理。最后一次 residual 写 ACK 与最终 block Fence 之后才发布两个 state root 和 generation。当前预归一化输入与八命令 core 仅是这个完整链的中间验收，不能关闭 block。

预计超过十分钟的生产 top 构建/数值执行使用 GitHub 持久 job。已完成的源、ELF、RTL 和输入身份可保全复用；没有终态回执的本地会话不重复当作成功，也不从零反复启动。

## 每一步的完成条件

每次加入生产运算后，先在同一 DUT、同一物理 DDR 服务内跑 cold→carried 的小实际数据链；只初始化原始输入、原始权重、常数和初始 state，中间区使用哨兵。独立审计全部写请求/ACK、各次完成时的共存内存、最终全 DDR、只读区和 guard。最后写 ACK 出错、读错、描述符 alias、背压和 reset/recovery 均不得提前发布输出或 state generation。

构建、fixture、实际输出、工具 ELF 与对应源码快照绑定不可变哈希。已验证旧证据保留原始来源；后继源码不得重绑定旧 PASS。Git 只存源文件、pins、哈希、精简数值摘要和中文计划；权重、NPZ、原始 tensor/DDR、可重建编译产物只留本地或必要 CI 临时工件。
