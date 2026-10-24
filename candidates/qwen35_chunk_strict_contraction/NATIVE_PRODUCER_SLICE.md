# PASS（仅 native 单 head producer→UT/QK 切片）/ INCOMPLETE（完整 block/RTL）：真实 Prep、chunk producer 与 native host_batch 切片

新增 opt-in `test_native_producer_slice.py`，复用已有 synthetic raw Conv/AB/A_log/dt_bias fixture，经原 InputPrepOwner/TypedInputPrepDriver 实际计算并发布 128 个不同 token。仅 head 0 活动，固定格式内其余 15 个 head 为零填充；并未执行上游 convolution、投影或真实模型权重。

随后构造原 ChunkOwner/TypedChunkDriver、真实 receipt-bound R2 Vector16，明确 host_batch=True、默认 fatal mask 30。不替换 `_compute`、`_op`、`_mul_add`、native 函数或标量 exp。实际执行 chunk 0 的累积 gate、decay/pair、派生矩阵与 UT/QK；最后 QK 写 ACK 完成后，接受首个 solve_v 读，再由原协议 abort/drain。最终必须为 Aborted、chunks_started=1/completed=0、未写/发布 output/state，也未推进 generation。因此不是成功完整 chunk、M128、block、全部 heads 或 RTL。

参考路径不向实际内存提供数值：
- 全部 128 行 Prep 共 819200 FP32 words，包括固定格式填充，使用既有 Fraction/RNE oracle。
- 87040 个 chunk producer words，包括所有 gate/Q/K/V/派生/转置/pair 矩阵，使用独立 NumPy 分离舍入及既有 exp oracle。
- UT 与 QK 各 4096 words，K 递增，Mul 后 Add 分别 FP32 舍入，最终再乘 pair。
- Fraction/exp oracle 核验的是本项目现有近似算术配方，不是与官方 PyTorch 的数学精度验收；没有全平面所有算术中间值/异常 flags 的独立 oracle。

实际 native 65536 次 Mul→Add host batch 和 5280 次 single 调用，共 1097728 Mul lanes、1050784 Add lanes；每个完整 UT/QK 各 32768 batch 加 256 pair single。所有这些是软件操作计数而非硬件周期。包括 Prep 发布前最后 ACK 背压、两个矩阵最后 ACK 背压、实际 accepted-read abort/drain、同一共享 scalar/vector 租约释放与绑定身份前后检查。现有 fixture decay 很温和，不覆盖 exp |x|≥80 饱和或真实模型 UF 问题。

执行需显式已有 R2 严格构建 receipt 的 `GDN_VECTOR16_FINITE_MUL_UF_LIBRARY`，不自动编译。无该变量会 skip，skip 不算 PASS。准备预算为 1 CPU、512 MiB 地址空间、50 秒 CPU、55 秒 payload alarm、外层 GNU timeout 60 秒加 2 秒 KILL；payload 除两次固定只读 git show 外禁止进程派生及网络，仅允许指定 R2 库和当前进程浮点环境查询。不继承旧 strict hook 或 synthetic phase PASS。

R1 实际尝试在 Prep admission 前失败，1 测试 0.200 秒 error。原因是 runner 禁止所有 subprocess，而原 Prep.source_identity 必须调用只读 `git show HEAD:chisel/continuous_prefill/src/main/scala/heteronpu/continuous/GdnInputPrepOwner.scala` 验证既有提交源码。没有产生数值 PASS，也没有取消来源核验。R1 日志/结果保留。

R2 仅放行 admission 与成功发布两次完全相同的只读 git show，固定 cwd、argv、受控 PATH 所选且哈希固定的 git executable，最多 2 次，成功流最终必须恰好 2 次。原 subprocess 10 秒 timeout 不改；其余进程操作/网络禁止，外层预算仍覆盖所有子进程。只读源码验证不等于编译或启动硬件仿真。R2 根实际 1 测试、0 skip/error/failure，unittest 5.427 秒、payload 5.551884267 秒、exit 0。1684 个列明文件执行前后哈希一致，实际两次 git show，未编译。此为 GNU timeout 监督，不冒称另一个 owned-process-group supervisor 已运行。

Prep 的 819200 words 中，head 0 的活动字段为 49408 words，其余 769792 words 是格式零填充；87040 producer words 也包括 gate padding 与 pair 上三角零。不用填充字数冒称活动计算量。完整数值边界比较通过不表示每一步 native 中间值及 flags 都独立核验，issue flags 仅核 {0,1} 范围和计数。
