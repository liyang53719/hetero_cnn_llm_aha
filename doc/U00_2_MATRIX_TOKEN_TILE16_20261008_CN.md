# U00.2：实际16-token Matrix tile门禁（执行前范围）

在已有默认关闭的Matrix→Norm→SharedL2→RoPE候选中增加显式tile16模式，
复用现有Matrix16×32/512 lane及真实1,572,864B SharedL2，不另建架构top。
现有tensor owner实际每次只使用一行，重复加载每token权重；本轮把最多16个
真实H1024输入打包进既有64KiB activation staging，让每个32列权重tile被活动行共享。
片上packed staging按tile-major固定16行排布，仍位于既有SharedL2。
后续逐head/row Norm256和partial64 RoPE只在明确写ACK后复用单头缓冲。

执行前冻结baseline/AVX2各4命令：cold token0..15 Q8/K2与carried112..127 Q8/K2，
共32选定token、320头/来源。每来源294,912个Matrix K步包、150,994,944个活动
FP32累加器观察值。实际RTL必须核对独立整数顺序FMA与独立C fmaf，原native
max_abs≤0.03125、mean_abs≤0.005不变；失败保留且不得用RTL匹配替代源精度。

补充tail、跨tile、位置、权重复用、capacity/alias、背压、同周期/延迟ACK、reset、
故障及恢复；源快照、逐文件哈希和独立trace/counter均需复核。未运行项不得标通过。
固定资源全block useful-wall分母不变；活跃行增加不是完整block90%或PPA结果。

16行门禁通过后才按8个tile推进M128全头实际回放。此轮不声称完整M128、
generic Command128、位置系数生成/cache、KV/Attention/FFN或三模型完整block完成。
U00.2 ongoing、U01 to do；默认路径保持原状。Git只含源码、pins、哈希和简短摘要；
checkpoint/NPZ/memh/二进制/完整trace均在临时或忽略区域重建，不进入Git。

## 实现与终态

本轮本地终态为 `PASS_Q8_K2_TOKEN_TILE16_RTL`。
结果、独立复核和互斥周期账本分别位于：

- `reports/execution/U00_2_MATRIX_TOKEN_TILE16_20261008/result.json`
- 同目录 `independent_review.json`
- 同目录 `cycle_phases.json`

`candidate_tile16_i` 在命令接受时快照，并且只允许与 tensor 模式一起启用。
每批最多16行，activation先以每token一条1024×2B DMA、目标stride64B及逐行byte-enable
装入既有64KiB区；同一批所有head复用activation，每个32列tile的64KiB权重只加载一次。
片上packed按 `tile*1024+row*64` 排布，Q固定保留16KiB、K保留8KiB，tail也不能缩小该保守跨度。
实际Matrix所有活动行参与每个K的FMA；每头全部packed存储ACK后，逐行gather进入原Norm/RoPE。
每行末端DDR ACK才增加completed_heads；最后一头最后一行完成后才一次增加整批completed_tokens。
未确认的失败批次不会被记为完成token，已经提交的外部写入不承诺回滚。

本轮还修复了实际payload中原有的非有限检测只检查row0的问题：复用既有32个转换器扫描全部
活动行，任意活动行NaN/Inf或BF16-RNE溢出都会在本tile任何写入前拒绝。没有增加算术阵列；
旧默认、FP32和单行候选保持原时序。独立旧HEAD复现了坏row1仍status0并写出16行，
修复后专门RTL覆盖32个候选用例、18个整tile拒绝、2个reset；31个legacy用例仍通过。

## 实际RTL与数值覆盖

- baseline/all：49个事务，10成功、35预检拒绝、2故障、2reset；450,560个真实Matrix输入/输出包，12,800个明确L2写ACK，6,178个同周期ACK
- AVX2/main：4个主命令，294,912个真实Matrix输入/输出包，9,728个明确写ACK，4,726个同周期ACK
- 两来源主门禁共640个head-token观察值、301,989,888个活动FP32逐K累加器值；实际RTL逐包检查全部512个lane，tail未活动行必须为零
- 17-token K成功用例真实经过第二个batch并完成单行tail；另覆盖1/3行tail、真实1.5MiB末端、完整保守跨度别名拒绝、外部sideband扰动、延迟及同周期ACK、末行末头DMA错误、在途reset和恢复
- 两来源所有选定head及8个主命令native门禁均通过；最大Norm误差0.015625，最大RoPE误差0.03125恰达原上限。max_abs≤0.03125及mean_abs≤0.005均未改动
- 4个补充cold token16 K head来源单独计数，完整独立整数/C核对通过；不能把它们混入预冻结的primary分母
- Q gate保留本次真实Matrix原始projection；没有把native projection注入硬件。完整producer/native block audit仍为baseline=false、AVX2=false

生成HardFloat RTL SHA256仍为
`5d4cf714637a579a50b9fd79eed3569c7e2a2bf39de9ba27775f0eb41d31aaf6`。
末端重新校验53份源码、全部临时向量/硬链接/官方receipt、硬件manifest，以及两份完整压缩trace和日志。
baseline与AVX2 runner仿真调用墙钟约1,873.13s和1,176.96s；这是软件工具耗时，不能作为硬件延迟或PPA。

## 可量化变化和周期边界

每个来源的4个primary命令共5,241,165个接受命令至done周期、150,994,944个有效FMA。
固定512-lane分母下，候选command-wall为5.6268406%，没有缩为active-window。
Q16分别2,294,959/2,295,722周期，K16分别325,595/324,889周期，约5.7%/5.0%。
这些仍不是完整block的90%结果。

同样N=16工作量的计数方程表明：Matrix包及权重payload减为旧逐token路径的1/16；
activation不再每head重复装入，Q/K分别减为1/8、1/2。这不是测得的16倍墙钟加速。
本次主门禁比旧两token窗口覆盖8倍有效算术，而Matrix包数是589,824→294,912，
不同工作量不能直接拿工具墙钟作A/B。DMA字节计数是成功ACK的payload字节，不是物理DDR总线带宽。

互斥周期账本逐命令严格闭合，两来源primary相同：

- Matrix operand read-owner等待3,228,083周期，占61.59%
- 接受read的周期589,824，占11.25%
- Matrix输入/控制/流水剩余区间489,997，占9.35%
- 权重DMA owner295,488，占5.64%
- RoPE DDR store owner164,480，占3.14%
- RoPE和Norm的边界间剩余区间分别102,827和99,200周期；完整细分保留在JSON

此账本包含随机test-fabric请求/响应/ACK延迟和显式512-cycle RoPE-store延迟；
它不隔离valid&&!ready stall或纯算术latency。250,989/294,912个Matrix输出握手发生在
read-owner等待周期内，约85.11%；因此Matrix输出事件必须作为重叠观测，不能再加进互斥分母。
Matrix输入fire时间戳没有记录，仅有真实接受总数。不能把所有read-owner周期都称为Matrix idle。
下一性能调查先针对串行operand-read路径及其延迟隐藏；不能靠删除分母或扩大阵列声称90%。

## 回归与可重建性

- 1,218项相关测试normal与Python -O均通过
- 全仓3,888项通过，仍为同5项既有失败，名单和日志SHA保留于结果摘要；不记为全仓全绿
- 独立source/trace/runner/payload评审通过；phase账本额外31项normal/-O和独立评审通过
- 新源码复跑旧单行实际RTL/all：45事务、7成功、21拒绝、10故障、7reset；141,319输出包独立trace通过。Matrix在途reset清空一个已接受包，输入141,320，不隐藏此差异
- 默认关闭source-closure lint通过；两种decode各8例、writeback10例/15,360值、iterator4个tail及5拒绝、descriptor planner3,072 tiles通过
- 既存VCS取向完整controller bench的Verilator混合赋值限制没有在本轮扩称解决；未执行综合/时序/PPA

标准入口：`python scripts/run_matrix_norm_rope_tile16_candidate.py --output work/NEW --jobs 2`。
低磁盘环境可指定 `--trace-directory /tmp/NEW_TRACES`，保持完整lossless gzip事件流，不删减lane。
周期后处理入口：`python scripts/analyze_matrix_norm_rope_tile16_phases.py --runner-summary work/NEW/summary.json --trace-directory /tmp/NEW_TRACES --output work/NEW/phases.json`。

本地执行使用当前刚完成的同一物化进程receipt衔接内部prepared入口，没有提供任意saved-array/digest CLI绕过。
CI标准入口自行重建全部固定官方来源。Git/CI仅保留源码、pins、哈希和简短结果；
所有checkpoint、NPZ、memh、逐K二进制、完整trace、生成RTL与可执行文件都留在临时/忽略区域。
MATLAB安装与等待用户登录的状态未触碰；未使用Voyager或用户电脑。
精确远端提交和CI终态须以发布后核对结果为准，本地PASS不替代它们。

## 下一门禁

在同一owner上执行8个16-token batch的完整M128 Q8/K2及全部native检查，并为更大的参考/trace
采用有界临时处理，避免靠片上扩容或磁盘盲目增长。17-token跨批成功和128范围准入故障测试
不替代这个全量门禁。之后按实际周期账本确定延迟隐藏优化，保留固定硬件分母。
generic Command128、系数生成/cache、KV/Attention/FFN、三模型完整block、PPA与MAC90%继续OPEN；
U00.2 ongoing，U01 to do。
