# U00.2：79bbe 完整 GDN 双 M1 数值回归

精确提交 `79bbe751b7b221023b02546860e213c16c07b2ea` 的
[run 38003994809](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/38003994809)
于 2026-10-10 03:56:55 UTC 完成。实际数值 job `114081479911` 和末 acceptance
job `114125809569` 均成功。已下载紧凑工件 `11658988052`，37515 字节，SHA256
`18ecbefb4eb99ea476ba5a0fd347fa954fb4a9eaaaba5cb6a915ab59639f3118`，与 GitHub
元数据一致；552 个源码 SHA 全部匹配该不可变提交，104 个 fixture/input 身份
及输出、原始日志、RTL、ELF 摘要完整保留。没有重跑模型或将旧证据绑定到新源。

实际范围为 Qwen3.5-0.8B layer0 完整 GDN block：原始 hidden 经 DUT input RMS、
QKV/Z/AB Dense、Conv4/SiLU、QK 与门值准备、FP32 状态递推、gated norm、O、
残差、post RMS、gate/up/SiLU×up/down、末残差和双状态 fence。cold token19 后
在同一 DUT 中直接执行 carried token92；中间无 reset 或参考状态注入。每次
17 条命令、216 条 descriptor record、16 个 owner job，generation 为 0→1→2。

每次实际写回并确认 1,194,048 字节，即 18,657 个 64 字节 beat；两次合计
2,388,096 字节。第二次从上次真实已 ACK 的内存读取 history 768 beats
（49,152 字节）和 FP32 state 16,384 beats（1,048,576 字节）。末 pc16 fence
本身没有 payload 写 ACK，验证的是之前所有写回后接受的终端提交。

两次完整 canonical 比较均为零位差，独立原 native 完整 block 门也通过。
门限保持：BF16 隐藏节点 max/mean 为 0.03125/0.005，末 residual2 为
0.05/0.01，FP32 state 的 atol/rtol 均为 1e-4。本次 fresh 样本 cold residual2
有 2 个原始位差，最大误差 0.0001220703125、平均误差约 1.49e-7；carried
residual2 零位差。state 分别有 131869/161405 个原始位差，最大误差
1.7881393432617188e-7/1.1920928955078125e-7，原容差内失配均为零。
不能把容差通过称 native state 位精确，也不能沿用旧 d7 两个 residual2 都零
位差的样本结论；历史结果保持其原输入和源码身份。

同源 driver 在每次完成 launch 时确实硬检查实际公共端口 `io_usefulMacs`
等于 21,528,576，两次合计 43,057,152。独立参考中的 43,515,904 padded FMA
不是实测 executed MAC。compact 与完整 GitHub job 日志没有保留
accept→首次 terminal 的两个周期端点或 executedMacs，因此完整周期和
Matrix 全时段利用率仍为空，不能用最后 COMMAND cycle 或仿真壁钟补造分母。
源码架构的 GDN M1 0.09381854% 乐观上界仍属于另一种证据。

此次完整 block 的 fault injection、reset、checkpoint restore、M128、后继层、
35B 和 PPA/90% 未完成；Attention 的 native 原失败也不由本结果覆盖。
U00.2 ongoing、U01 to do、C02.2 OPEN，不关闭跨模型大项。

可复核摘要与逐源审计见
`reports/execution/U00_2_HOST_GDN_BLOCK_CI_79BBE_20261010/`。这些文件只保存
摘要和哈希；原始 tensor、NPZ、权重及可重建 payload 未加入 Git。
