# U00.2：GQA 选择接入与完整 block MAC 统计

日期：2026-10-09 UTC。Attention 完整 block 新数值门仍为 PENDING；M128、35B、
官方完整精度合同及物理实现未验收。U00.2 ongoing，U01 to do，C02.2 OPEN。

## 选择器候选已通过的范围

[run 37998493748](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/37998493748)
在 22:34:49 UTC 成功结束，门实际耗时 816.557 秒，保持 1800 秒预算。
诊断提交为 `aa9ac8277217c20c10652aa639f329e44184d6b2`，冻结生产基线为
`6959810545203d5f9508075b311dba52f1bee0c9`。实际 Chisel 选择器 1 项与原 GQA
owner 6 项全部通过。原完整 top SV SHA 精确复现，候选新 SV SHA 为
`88253f7c5967f914eed1875d49d82446c4f1673011fa42cef7fdfc65e6c81eda`。

56 个生成模块中只有 Bf16CausalGqaOwner 原文变化，其余 55 个及模块外原字节
完全相同，没有去除注释或规范化。生成 C++ 的宽拼接调用从 8192 个降至 128 个，
最大位宽从 131072 降至 4096；这不是实测仿真提速或 MAC 利用率提升。
独立 19 项检查核对全部 Git 源码、619→620 构建源码闭包、工件及保留源码哈希，
并从 4 个已保存 C++ 调用文件精确重放全部 128 个调用。

工件 `11649015099` 为 1,093,315 字节，SHA256：
`b414ccefc11eb37f6980606aefc5fa61cda8e1e506c517b25232dc1cb5a9f174`。
候选 owner SV 原文因 12 MiB 保全上限未上传；模块比较结论有运行回执，不能
称本地已重新比较未保存的全部候选 SV。首轮 8e2d895 的严格模块 FAIL 仍保留，
其额外变化原因不补写为已证明仅注释变化。

生产源码采用精确候选 SHA256
`d4c1047d275fa0b38d9498fdf6c22018f52138b21a49e55866661a4d4e635cd9`。
对应 Spec SHA256 为
`91448d1935bb57b917e7065bf23c91f35ac3b33dc2066d5b2b8e311993833a13`。
原 Matrix 浮点运算、8 个物理 slice、Scalar、iDMA 和状态/发布协议不变。
候选 owner 测试的 Matrix 端点为软件 FMA；完整真实 Matrix 数值必须由后续
22 命令 block 门执行，不能用这些小门替代。

## 下一次实际执行与计数边界

现有 Attention Block workflow 只构建一次完整 ELF。先用同一 fresh 输入和
ELF 独立执行两个 4096 周期前缀，比较实际 AXI 全数据事件 SHA、计数、终态和
实际内存摘要。36 个构造/reset 周期包括在前缀内，raw payload 只留本地，
compact 只输出 hash/标量。前缀 pc0 是 input RMS，不推断 GQA 已活跃，也不
授予数值通过。

随后保留原两个进程、各连续两个 M1 launch 的完整 pass 和末 residual ACK
故障用例，实际历史 KV 来自上一 launch 写回。总预算 18000 秒、build 7200 秒、
各数值 case 3600 秒均不变；两个前缀各最多 240 秒并消耗原总预算。
完整 top 记录新实际 SV/ELF/源码身份，不能沿用上述冻结 core SV 身份。

新增只读 driver 统计来自现有公开端口：launch 接受前边界至首次 terminal
result 的周期、每 pc completion 周期、useful/executed MAC、Matrix wide issues
与 stalls、AXI beat/ACK、iDMA transfers。不增加 clock/eval、请求或随机数。
时间区间包含 launch 接受那一拍，排除 reset 和后续刻意保持 result 的 7 拍。
useful/executed 为每 launch 清零的 64-bit 成功 owner 回执累计；全局 Matrix/
iDMA 为 64-bit 累计值，按 launch 差分。故障样本不计算成功整 block 利用率。

固定 Matrix 分母为 `8 × 16 × 32 = 4096 MAC/周期`，一乘加算一个 MAC。
整 block 有效利用率按 `useful MAC / (4096 × 完整周期)` 计算，包含 Scalar、DDR、
空闲 slice、时钟门控与 bench 注入的等待。stalls 只表示 Matrix step valid 且
not-ready，可能与其他等待重叠，不能将其与 DDR/Scalar 数字直接相加。
Scalar 逐 opcode、owner 内部 cycles 尚未公开，明确留空，不造互斥周期桶。

## 生成 RTL 前的 GDN M1 架构检查

新增 `python -m heteronpu.qwen35_arch_utilization --repo .`，由源码固定 hash
核验后在实际 EDA 前运行。它只输出乐观架构界，不输出预测值或 RTL 实测值。
M!=1 拒绝；不把 M1 乘 128 冒充 M128 调度。

当前每 M1 的 Dense 有效 MAC 为 21,528,576，至少 84,992 次宽发射。
仅有一个有效 token 行；AB 的 N32 又只启用 8 个 slice 中的一个。
因此有用/启用 slice 的执行量比为 6.25%，固定全阵列的 Dense 理想发射利用率
上界为 6.18411145%，两者都不是整层 RTL wall 利用率。

递推每 token 有 1,839,104 个基本 FP32 Add/Mul 请求，另有 16 次 exp。
单在途 Scalar 的 idle→normal→done 至少 3 拍，Host 等 owner 完成才发下一命令，
与 Dense 不重叠。仅计这些必要成本已给出 `T >= 5,602,304` 周期，因此完整层
固定 Matrix 有效利用率上界为 **0.09381854%**。此界省略 exp、其他 Scalar owner、
访存/ACK及控制成本，不能称周期预测或实测。它明确暴露当前逐标量递推调度
的结构问题；本次继续数值验收，不借此开展性能微优化或改变 FP32 state 精度。

既有通过的 GDN 双 M1 记录了 43,057,152 个 useful Dense MAC，但 compact 和
已上传 job log 未保留原始完整周期或 executed 计数，不能补算真实整层利用率。
43,515,904 是参考 padded FMA 步数，不能替代硬件 executed MAC。

本次生产修复使用一次既有完整回归批次，不使用 skip-ci。原规划 19 jobs 的
3250 runner-minutes 是显式 timeout 上限之和，并非预计 wall time 或实测成本。
候选诊断 workflow 不随本次生产文件变化重新触发。完整数值门终态前不关闭
C03.2、C04.2、C05、S01、Q35A 或其他上层任务。
