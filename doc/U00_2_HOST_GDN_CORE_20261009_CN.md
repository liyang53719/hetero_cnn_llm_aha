# Qwen3.5-0.8B GDN core 的生产 Host 接线

本次是默认关闭的 policy v2 命令链，生产数值状态为 PENDING。独立 owner、小控制 RTL 与 Host RTL 生成通过，不能替代同一生产 DUT 的完整数值终态。前一条 v1 Dense→Conv 的 a41749 精确提交继续原 GitHub 作业，本次不改它的证据。

## 生产递推写回故障与修复边界

2026-10-09 的精确提交 `904dccf2830d8caa50501041ca4895995ac41ad8` 实际 core CI 在 cold 的 pc5（第 6 条命令）返回 Memory=3。最后成功的物理 ACK 对应 head0、row127、column16 的 FP32 state；随后输出高半 32B mask `ffffffff00000000` 被真实 retained iDMA 的低位连续 prefix 契约拒绝。原独立 owner 测试直接接受该 mask，遗漏了生产接口限制。原失败日志、输入与源码身份保留，不能改写为数值通过。

本次修复把相邻两组 16 个 BF16 输出保留并合并为完整 64B，只有两组 FP32 state 全部 ACK 后才发送输出；原 FP32 算术、状态精度、顺序及官方门限不变。合法 valueDim 必须含完整两 tile，奇数 tile 几何仍拒绝。独立 owner 与生产日志审计同时限制完整 mask，并检查最后一对、第二 tile 错误、配对中 reset 和最终 ACK 屏障。修复后独立 owner 的 3 项协议/尾 pair 测试和两实际 head×128² cold→carried 均通过，每次 131584B 全 ACK，固定算术全位一致。真实 pinned iDMA 在 streaming 配置和 shared hub 两种结构中分别 31/31 通过，明确复现旧 high32 零 AXI 拒绝、完整 pair 0/31/63、最终 B 延迟 40 周期及错误屏障；这新增的是普通 MemoryRequest store 契约验证。生产 adapter 没有改变。新生产整链 CI 终态前仍为 PENDING。

标准 Command128 的八条命令依次执行 QKV、Z、AB32 Dense，Conv4/SiLU，Q/K L2 与 g/beta 准备，FP32 recurrent，gated RMSNorm 和双状态 Fence。AB32 由原始 A/B 两份 N16 权重按 K 主序拼接，不能用预计算 gates。所有中间输入来自实际已 ACK 的物理 DDR 写回；第二个 token 使用第一个 token 的 history/state。预期两次 M1 launch、16 条命令、14 次 owner 运行、2,320,512 有效写 ACK 字节。

生产资源仍为同一 HostBlockTop、StreamingDenseOwner、MatrixPipelineService 和 iDMA。四个 GDN owner 共用原 Scalar 服务；core profile 不实例化未用的 legacy ScheduledSiluOwner。局部 emission 记录了一个 BlockScalarFloat 和一个 MatrixPipelineService；它只证明该源码版本的结构，不证明数值、PPA 或时序。后续的前端只读参数 alias 比较修订单独编译并做控制回归，不把这次 RTL 哈希重新绑定到后继源码；CI 将从最终提交全量生成。

公开描述符使用 GDN_POLICY v2 和 GDN_AUX_ROOTS 0x23。BF16 QKV/Conv、FP32[1,6400] prep、FP32[2048,128] recurrent state，以及原始 FP32 norm.weight 分别检查 dtype、维度、步幅、权限和实际字节数。首次上下文必须 cold/gen0；carry 必须引用上一成功 Fence 的两个 root 和 generation。七组权重/参数绑定随该状态上下文保留，不能在 carry 更换，也不能被后续输出覆盖。各命令保留自己的事件前驱，末 Fence 只有在全部生产者成功、最终写 ACK 和 completion 消费后才共同发布两个 root。

独立算术门禁保留原来源和原范围：

- InputPrep 用真实共享 Scalar 核对两头 cold/carried M1 的每一步 FP32 请求/结果和四输出；Softplus 默认关闭，新增范围与舍入不改变旧 Scalar 策略。
- recurrent 用两个实际头的 128×128 FP32 状态完成 cold→carried。carry 从前一真实写 ACK 的 state 读取，未降为 BF16。
- gated norm 的单 job 已覆盖完整 16 头、两个 M1 用例，共 4096 BF16 输出对固定算术逐位一致。
- Conv 原独立门禁保留官方比较中的正负零位差；数值 0 ULP 与逐位相等分别报告。

两 token 参考使用固定模型 revision 2fc06364715b967f1860aea9cf38778875588b17、固定 Transformers revision 14e738b5d0cc69aa27a95dde272aea41fde44f2f，以及真实 embedding token 19/92。66 个独立整数/C 投影任务共计算 17,301,504 次 FMA，其中 AB 的参考零填充仅用于共享 oracle；实际 Dense 有用 MAC 是 16,842,752。原 Dense/Conv 的 max_abs≤0.03125、mean_abs≤0.005 与同输入 Conv/SiLU ≤1 BF16 ULP 门禁继续执行。Prep、Softplus、recurrent 和 gated norm 的官方误差保留诊断，不从整 block 门限推导新的 stage 通过。先前完整 native BF16 拒绝结论仍保留。

持久 CI 分为一次构建和一个连续的真实 cold→carried 运行。构建工件只交接 ELF、RTL 和来源/工具回执，接收方先验证精确提交、受信 SHA、文件白名单和所有内容哈希。每个数值作业从固定来源重新生成活的参考上下文，初始化仅原始输入、权重、常数和初始状态；中间区放哨兵。审计逐 byte strobe/ACK、每条命令后共存输出和最终整片物理 DDR。Git 只保存源码、固定来源、哈希、精简摘要及计划，不保存权重、NPZ 或原始 DDR。

尚未完成的是本次生产数值终态、core 级真实 fault/reset/restore、M128，以及完整 GDN block。当前输入仍是官方 input RMSNorm 的输出。完整 block 必须由 DUT 从实际 layer0 hidden 开始计算 input RMSNorm，并继续 O projection、残差、post RMSNorm、gate/up、SiLU×up、down、第二残差；双 state 的最终 Fence 必须移到这些下游结果全部 ACK 之后。不能把八命令 core 验收当作完整 block。

这是 C03.2/C04.2/C05 的局部接线子门，S01/Q35A 与完整三模型验收继续推进；U00.2 ongoing、U01 to do、C02.2 OPEN，不关闭大项。
