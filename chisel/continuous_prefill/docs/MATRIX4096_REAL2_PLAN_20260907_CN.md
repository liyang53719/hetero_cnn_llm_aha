# 4096-MAC Matrix：real16 双层重新验收

基线：main@da3ae97e73eabd24874514d9fc301a5ceaea1e5a；已通过的 512-MAC 双层证据为 reports/execution/REAL16_TWO_LAYER_9f06249ca11f/numerical。保留旧证据，不改写历史数字。

用户批准将单个逻辑 BF16 Matrix 从 512 改为 4096 MAC，时钟仍为 800 MHz（1.250 ns）。本轮选择 16×256，以利用 real16 的全部 token 行；内部以八个 16×32 原算术子阵列组成一个共同 Matrix owner，不增加 Host 调度引擎或第二套 iDMA。BF16 乘法、FP32 累加；不改变每个输出的递增 K 顺序、舍入规则或原 42-command Host 图。

开发和验收顺序：
1. Chisel 扩展共同阵列接口、权重喂数和完整输出 tile 写回；只修改设计源，不手改生成 RTL。
2. 用小尺寸真实 Host/iDMA/Matrix 数值和定向错误/回压测试验证切片握手、尾部和只启用部分子阵列；再执行真实 H1536/F8960、16 tokens、两层不同权重。
3. 两层共 42 commands、430 descriptors、38 jobs；检查 1,409,024 个 FP32 输出，并与冻结 512-MAC 的 actual 文件逐字比较。第二层 X 直接指向第一层 Y；禁止 BlockLaunch 旁路、Host 层间复制或 golden 注入。
4. 同一请求统计 wall cycles、useful/executed MAC、DDR bytes、逐命令时间；报告实际加速比及 useful_MAC/(wall_cycles×4096)，不能用 8 倍资源推算 8 倍性能。
5. 只有完成完整数值日志和远端回读，才记录通过。正式 800 MHz DC、SRAM 宏映射及面积/功耗另行验收；代码、命令和验收由开发侧完成，本地 agent 仅复核和执行。

峰值约定：4096 MAC/cycle × 800 MHz = 3.2768 TMAC/s；2 FLOP/MAC 口径为 6.5536 TFLOP/s。此为理论资源峰值，不是已实现持续吞吐或物理时序签核。当前单在途 iDMA、FP32 容器权重搬运和串行 SFU 仍可能限制加速。

本轮先闭合 real16 两层，之后依据实际收益决定是否推进 real32/33；暂不扩展另两个模型。旧临时文件、失败日志、checkpoint 和原始证据全部保留。
