# Qwen3.5-0.8B：生产 Host Dense→Conv4/SiLU，数值验收待 CI

状态：PENDING。默认关闭的真实生产路径已实现、独立 owner 与控制门禁通过，完整 Host 构建成功；本地四命令仿真在没有终态回执的情况下中断，不能写为数值通过或数值失败。后续超过十分钟的生产数值运行交 GitHub CI，保留原始中断与源码身份。

本次交付仅为 C03.2/C04.2/C05/S02/Q35B 的局部集成增量。U00.2 仍 ongoing、U01 仍 to do，C02.2 原官方完整精度门禁仍 OPEN，所有关联大项状态不关闭。

## 实际实现

标准 Command128 经现有 TypedTensorReader、HostBlockCommands、QwenOwnerKernel、StreamingDenseOwner、同一个 MatrixPipelineService 的八个 Matrix512 slice 和同一个 iDMA 执行。新增 GdnConv4Owner 只发送外置 Scalar 请求，借用 core 原有 BlockScalarFloat；没有添加第二个 Matrix、Scalar 算术实例或 iDMA。

四命令为 Dense(token19) → Conv cold → Dense(token92) → Conv carried。Dense 为 BF16 A[1,1024]×W[1024,6144]，按 K0..1023 顺序 FP32 FMA 后 BF16 RNE。Conv 权重/history 为 BF16[6144,4]，每次 FP32 乘加分开舍入，Conv 后先 BF16 RNE，再算 SiLU 并终端 BF16 RNE。

Conv 只能读取前序 Dense 的实际 ACK 写回；carried history 只能读取前序 Conv 的实际 history 写回。D 和 history 是两个独立 span，仅在所有写 ACK 及 Host completion 接受后发布并推进本子链 generation。内存以物理地址为唯一索引，中间区及 guard 初始均为哨兵，禁止预填参考输出。

内部 owner kind 明确扩为四位，Conv=8；旧 kind 含义不变，未知 kind 拒绝。公开 GDN_POLICY=0x21、GDN_STATE_ROOTS=0x22 均使用既有描述符链；五个 typed tensor 的 bounds、dtype、stride、权限及两两 alias 在发 owner 前检查。

## 已验证边界

- 原 Scalar 77 向量和新增 18 个显式 IEEE RNE 乘法向量通过。op6 仅允许 underflow/inexact，保留 invalid/div0/overflow/nonfinite 拒绝；旧 Mul 下溢策略保持。真实极小乘积 `83d70000 × 02200000` 的正确 RNE 结果为负零，渐进下溢的非零 subnormal 也逐位验证。
- 独立 Conv owner 覆盖全 6144 通道 cold1、carried1、cold16、carried16，共 208896 个输出对固定算术逐位一致。官方数值 BF16 ULP 为 0，原始位差 9/9/116/116 均为正负零，不能称官方逐位相等。M16 使用组合输入，不能代表完整官方连续 block。
- 前端四个控制测试通过，包括新 GDN policy、五根地址、读读 alias 拒绝、跨 launch history、最终 ACK/代次及两个旧前端回归。该测试使用站位 owner，仅证明控制协议。
- 生产完整构建一次 EXIT0，18 分24秒；实际进程树峰值约3.006GB，最低可用 RAM 1.485GB，无重试。二进制 SHA256 为 `ff4661df62a3bfdcf3bb4db7264c18e25df20295c6539773d2e0ecca9ceeaaf6`，RTL 为 `8eb8eb96211ed6dd5e0da762fb113c754e4e762132650084e4bb9e15108582ee`。

## 原始输入与中断

固定模型 revision `2fc06364715b967f1860aea9cf38778875588b17`、Transformers revision `14e738b5d0cc69aa27a95dde272aea41fde44f2f`。输入来自真实 token19/92 embedding 经官方 layer0 input RMSNorm；inputNorm 不属于本 DUT。全部14份 layer0 权重保持原精度。48头、12582912次 FMA 的整数/C 双参考已通过，末端 native 指标保持原门限；没有执行完整前缀捕获或完整 block。

本地复用封存 fixture，并独立重算约45秒认证所有输入和参考字节。实际 Host 启动后，资源记录停在2026-10-09 04:23:16 UTC；随后 poll 返回 Unknown，退出回执不存在。日志只到第一条 Dense 的写回，已完成命令数为0。最低记录可用 RAM 约2.746GB，没有守卫触发或数值失败标记；中断原因未知，不推断 OOM。

紧凑事实、完整源哈希、owner/控制边界及中断清单在 `reports/execution/U00_2_HOST_GDN_DENSE_CONV_20261009/`。本地构建绑定55785dd基线上的冻结源快照；CI必须另验证新精确提交，不能把该基线SHA当本次数值提交。

## CI 与后续闭包

先完整四命令 pass，再运行末 history ACK 故障、物理输出 alias、同 DUT reset recovery；每个 case 从自己的 reset 起执行完整真实前序命令。独立 Python 校验器从实际六个 span 回放每个成功写 ACK，检查每次完成快照和全部12947456字节 DDR，含只读区、guard、历史输出、native原阈值与正负零差异。跨 job 只传必需程序/RTL和源/工具身份；权重与参考在执行端按固定来源重新取得，Git不存权重、NPZ或任何编码张量。

本次未接 recurrent FP32 state、gated norm、out projection、残差或 FFN，也未执行 Host M128。下一生产链依次接真实 Dense Z2048/AB32 → QK L2与g/beta → FP32 recurrent → gated norm，复用同一 Scalar/Matrix/iDMA。完整链必须把 Conv history 和 recurrent state 都写入 staging，在最后 fence 后原子推进双域 generation；checkpoint restore 必须来自真实成功回执，不能由 golden 重建 state。深 core 草稿与本次 v1 发布分开，未完成项不混作通过。
