# 0.8B L0 真实 M128 chunk64 连接（TEMP / INCOMPLETE）

复用已验证 SHA 的真实权重生产者 prepared[128,6400]，不重新计算RMS/Dense/Conv/RawPrep。新增独立 NumPy 向量化 scalar_core chunk 方程：完整64×128矩阵、64项下三角 solve、128×128跨chunk状态；每个head执行chunk0和chunk1，非循环M1。所有矩阵乘积使用逐K的独立FP32乘法再加法，不使用matmul/FMA/BLAS改变顺序；状态仍FP32、最终输出BF16 RNE。没有运行Chisel或RTL，也没有改变固定4096资源。

保留原scalar fatal tiny-inexact策略，乘法的FP64中间精确容纳FP32乘数48有效位，转换FP32后检查tininess_after/inexact；加法使用FP64中间，tiny-inexact边界仅用于拒绝，flags整体仍未获得硬件资格。每个失败操作用独立Fraction校验精确RNE及tiny/inexact。源准备阶段仍有NumPy sqrt/div等候选限制，不能由本后缀反推全链精确。

最终实际运行：16head，12head完成两个chunk及状态输出；head0/3/11/13在chunk0检测tiny-inexact而停止该head，其他head独立继续。head0 phase6 intra 的 b90b2091×05d1243c→801c6a52，head3/11/13在phase2 derived。这里的phase/索引是独立参考执行序，不声称是硬件首先报错的周期/调度。FAIL_CANDIDATE_ORIGINAL_FATAL_UNDERFLOW 不等同新增硬件FAIL；旧head4实际硬件FAIL保持原身份不变。

不能把失败head填零、跳过或换gradual策略继续形成完整block，故后半gate/O/FFN没有执行，完整五块仍0/5。不报告MAC利用率。

验证：n2/4/8非零小算例输出BF16及FP32状态与原scalar_core逐字一致；8个exp边界一致；4个真实失败操作的精确RNE及tiny/inexact通过。普通和-O检查均不依赖assert。所有输入/输出数组仅本地，包只收源码/pin/hash/摘要。

首轮摘要序列化因np.int64索引失败，保留first_serialization_failure.log；改为Python int后首完整运行session5693完成4.19s。补齐最终BF16输出物化后session28597正常exit0，完整重跑数秒；不迁移旧FP32最终输出hash，新RESULT为准。600sCPU/wall、2GiBAS上限。

复现：OPENBLAS_NUM_THREADS=1 timeout 600 python round_20261110T0933/l0_full/run.py；随后test_chunk.py。运行依赖既有已核验prepared及原scalar_core/rational_oracle，PINS列出SHA。
