# Qwen3.5-0.8B L3：cold128 软件结果（有限范围 PASS）

本批仅记录已独立审核的真正 128-token cold 软件计算：同一 Memory/owner/Matrix/vector/scalar 链，19 个 owner 全部终态、1 次 Matrix reset，56 个已实现 producer 域通过原门限。**不是完整 57 域合同通过**：`self_attn|aten.add.Tensor|2`（causal mask-add）没有独立原生计算结果，未伪造补值。carry128 未执行，L0 未在本轮重跑。

输出 131,072 个 BF16 元素：max_abs 0.0009765625、mean_abs 1.5411936828968464e-06，原门限 0.05 / 0.01；1,420 个 bit mismatch，不能称输出 bit-exact。最终 K/V 各 65,536 元素 bit-exact。56 域共有 6,937,600 元素，最大 operator abs 0.015625，原 operator 门限 0.03125 / 0.005；softmax 行和最大误差 3.6049095797352493e-07（门限 2e-05）。全部详细聚合与哈希见 COMPARISON_AGGREGATES.json。

参考使用官方 frozen revision 的 fresh capture；完整 cold+carry 两窗 seal 都读取验证，但仅 cold 输入/三角常数被物化、执行与比较。官方中间值没有注入实际算术执行，比较在 19-owner 终态保存后开始；完整 seal 可能预先读取参考字节，因此这是源绑定的参考分离，不是操作系统读隔离，也不是独立三角函数生成。

原运行模型 wall 3057.8420788209187 s，监督 wall 3070.2519433249254 s；采样 group CPU 高水位 3038.82 s、RSS 高水位 557010944 B，最大采样间隔约 0.15137 s。未保存最终 wait4 CPU 合计，采样不是连续峰值；CPU 硬限逐进程而非全树。cleanup 限原锚定组和已观测身份，保留 leader 两次空扫描后回收；不能排除未观测的逃逸。SIGKILL 记录针对已终态 zombie 清理，不是预算失败。

24,335 pins 的原前后收据是 source-bound 聚合计数，无逐项历史 PASS；独审没有重读全部 1.24 GB runtime/权重。91 个当前与保存源码、129 次实际数值文件读取及明确分层的 inventory 支持所列结论，不声称完整动态 loader/环境闭包。未保存的历史环境字段不能通过本包补写。

3,382,041 software ticks、2,415,919,104 recipe FMA 调用和 ACK 数仅软件源绑定计数，不是硬件周期、有效 MAC 或利用率。最终 Add 为实际 TypedElementwiseDriver，完成后才发布 cache generation；无独立 per-tick trace 重放。

本批无 Chisel/RTL/Command128、完整 4096-MAC、统一五 profile 同 RTL hash 或 PPA/90% 通过。旧 FAIL、L0 身份/源码漂移及 todo/ongoing/done 全部保留；13 done /14 ongoing /47 to do 的 canonical 未改，U00 ongoing、U01 to do。这里只补有限证据，不关闭整体任务。
