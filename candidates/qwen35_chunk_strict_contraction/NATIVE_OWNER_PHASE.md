# PASS（仅合成单相位 native 软件接入）：真实 Vector16 host_batch 与原 ChunkOwner 单相位接入

此测试只替换实例 `_compute`：先经真实 TypedChunkDriver 写入/ACK 三个合成矩阵，再调用原 `_matmul` 完整执行一个 UT 64×128×64 收缩。没有替换 `_op`、`_mul_add`、native 函数或原 tick/ACK/drain。`host_batch=True`，明确选择 `finite_mul_tininess_r2`，默认异常策略及 fatal mask 30 不变。scalar/exp 未改变，实际此相位不调用 scalar 算术。

输入是 seed 905 的合成相位边界，不是模型权重、真实 Prep/decay producer 或完整 ChunkJob 算法。完整相位耗尽后原 owner 必须以 `Protocol` 失败，因为 output/state 未写；不能把该预期失败标为完整 chunk 成功。其他测试覆盖首批 Mul 的 UF3 必须先于 Add 失败，以及首个结果写已接受后的 abort/drain。完整相位测试还悬停最后写 ACK。

预期覆盖：
- 32768 个真实 native host_batch Mul→Add 调用，以及 256 个真实 native pair Mul 单调用；不是 FMA。
- 4096 个最终 FP32 words 对照 NumPy 按 K 递增、分别舍入的 Mul/Add 和最终 pair。
- row 15 / col 0 的 16 lanes、128 K：4096 个 product/accumulator 中间 words 对照 strict integer primitive。独立期望 accumulator 跨 K 保存，另核 native 输入 accumulator、Add lane flags 以及每个 Mul/Add issue 的聚合 flags。该行的 16 个 pair 因子均非零，其中对角为 1。
- 没有完整平面的独立 flags oracle；native Mul lane flags 未逐 lane 保留，不能声称全部 Mul lane flags 已对照。
- 35072 个 read、1280 个合成输入 write/ACK 加 256 个结果 write/ACK，均软件事务，不是硬件周期。
- 无 library 环境变量时整组 native 测试会 skip；missing library 和错误 backend receipt 的负例禁止 CDLL，不能把 skip 算 native PASS。

运行必须显式提供已有严格构建 receipt 对应的 `GDN_VECTOR16_FINITE_MUL_UF_LIBRARY`。测试不自动编译，不下载依赖。根执行 5 测试（3 个实际 native 算术/owner 测试、2 个不加载库负例）、0 skip、0 failure/error，unittest 1.682 秒，含导入/测试的 payload 计时 1.838724377 秒，exit 0。运行使用 1 CPU、512 MiB 地址空间、50 秒 CPU、55 秒 alarm，外层 GNU timeout 60 秒及 TERM 后 2 秒 KILL；Python audit 禁止派生进程和网络，CDLL 仅允许指定 R2 库及当前进程的浮点环境查询。原构建库及 receipt 复用，无编译。

执行前独审发现观察者在 tick 后读取 position 会偏到下一 K，以及参考 accumulator 错用 native 输入导致仅一步比较；首次 native 执行前已修正为 tick 前 snapshot 和独立跨 K accumulator。根执行前后核对 1679 个候选 Python、CPP、ELF/receipt 文件哈希，公开回执只列相关源码与摘要，不上传全盘清单或本地日志。此为 GNU timeout/同进程限制，不冒称另一个 owned-process-group supervisor 已运行。

仍未覆盖真实 producer、第二 chunk/state carry、M128、全部 heads、完整 block、HardFloat/Chisel/RTL 或任何 MAC 利用率验收。旧 M128 软件 strict hook 回执不自动授予此 native 接入资格。
