# Qwen3.5-0.8B 第 0 层完整 GDN block 的生产接线

本次 policy v3 从真实 raw hidden 开始接通整层运算，生产数值验收仍为 PENDING。源码编译、独立 owner 的小型真实 RTL 和前端控制检查各有自己的证据；只有同一生产 HostBlockTop 的完整 cold→carried 终态与原官方精度门禁同时通过，才可称本范围完整 block 通过。既有 v1、v2 和旧 Qwen2 作业继续绑定其原始提交，不以本次源码重新解释旧证据。

## 生产递推写回故障与修复边界

2026-10-09 的精确提交 `904dccf2830d8caa50501041ca4895995ac41ad8` 实际 core CI 在 cold 的 pc5（第 6 条命令）返回 Memory=3。最后成功的物理 ACK 对应 head0、row127、column16 的 FP32 state；随后输出高半 32B mask `ffffffff00000000` 被真实 retained iDMA 的低位连续 prefix 契约拒绝。原独立 owner 测试直接接受该 mask，遗漏了生产接口限制。原失败日志、输入与源码身份保留，不能改写为数值通过。

本次修复把相邻两组 16 个 BF16 输出保留并合并为完整 64B，只有两组 FP32 state 全部 ACK 后才发送输出；原 FP32 算术、状态精度、顺序及官方门限不变。合法 valueDim 必须含完整两 tile，奇数 tile 几何仍拒绝。独立 owner 与生产日志审计同时限制完整 mask，并检查最后一对、第二 tile 错误、配对中 reset 和最终 ACK 屏障。修复后独立 owner 的 3 项协议/尾 pair 测试和两实际 head×128² cold→carried 均通过，每次 131584B 全 ACK，固定算术全位一致。真实 pinned iDMA 在 streaming 配置和 shared hub 两种结构中分别 31/31 通过，明确复现旧 high32 零 AXI 拒绝、完整 pair 0/31/63、最终 B 延迟 40 周期及错误屏障；这新增的是普通 MemoryRequest store 契约验证。生产 adapter 没有改变。新生产整链 CI 终态前仍为 PENDING。

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

本次两 token 的完整 CPU 参考已在 153.4 秒完成，138 片所有逐 K 位/flag 比较一致，39 份参考源与工具身份前后保持。cold 最终输出 max_abs=0.0001220703125、mean_abs=1.4901161193847656e-7，carried 最终输出零位差；FP32 state 的最大绝对误差分别为 1.7881393432617188e-7 和 1.1920928955078125e-7，原逐元素阈值下均无失败。全部 BF16 隐藏节点通过原 operator 门限，最大误差来自 carried QKV 的 0.0078125；同输入 Conv/SiLU 均为 0 数值 ULP。这仅说明本次真实两 token 的完整参考通过原门限，尚无生产 RTL 输出，不能关闭历史其他范围的 native 失败。

预计超过十分钟的构建和生产数值均交 GitHub 持久 CI：一次构建交接精确哈希的 ELF、RTL 与源码/工具回执，后续一个连续进程完成两 token 的 34 条命令。物理测试内存只以真实地址索引，每条命令检查已完成输出和所有未写字节；独立审计逐 strobe/ACK、所有完成快照、最终整片 DDR 及两域 carried 读取。Git 和紧凑数值工件不保存权重、NPZ 或原始 tensor；构建交接仅包含运行所必需的程序、RTL 和身份回执。

本地主源码编译通过后，完整 Host 的有界 RTL emission 在 56 秒收到 SIGKILL，exit -9，未生成 RTL。外部资源 guard 未触发，采样最低 MemAvailable 约 1.29GiB；没有足够证据指定 OOM 或其他原因。该失败及完整源/资源回执保留，未作本地重试，后续完整生成和构建交持久 CI。它不是数值失败，也不能算生成成功。

本次尚未完成生产整链数值终态、完整 block 的实际 fault/reset/checkpoint restore、M128、后继层及 35B。控制错误测试和独立 owner 的 reset 不能替代完整生产链恢复。U00.2 保持 ongoing，U01 为 to do，C02.2 原 native 门禁保持 OPEN；C03.2/C04.2/C05 只增加本次有界接线证据。
