# PASS：单 head 完整 M128 native 软件 staging；完整 block / RTL 未验收

合成原始 Conv/AB 边界输入先经过原 InputPrepOwner 的真实128-token计算，再接原 ChunkOwner：真正完成两个连续 chunk64、chunk1读取chunk0生成的state、完整输出及最终state写回ACK。没有替换 `_compute`、`_op`、`_mul_add`、native函数或原控制/事务方法。显式使用已有 receipt 固定的 R2 Vector16，host_batch=True、fatal mask 30及现有 scalar/exp 不变；legacy默认没有改变。

独立参考只用于比较，未写入实际 owner 内存：
- Prep 的819200个FP32格式words逐项对照现有Fraction/RNE近似配方，其中49408为活动head0字段、769792为其他head/格式零填充。
- 两个chunk的48个scratch矩阵，共403456 FP32 words，对照独立NumPy按K递增、乘后加分别舍入及现有exp配方。
- 完整16384 BF16输出words和16384最终state FP32 words逐项比较；BF16参考采用保留位/余数规则而非owner的偏置公式。
- 21,172,544个native lane操作是计数，不是逐项数值/flags比较。aggregate flags仅核0或NX及数量一致，不是完整独立flags oracle；这些参考不证明官方PyTorch/模型权重数值质量。

实际执行654336个native Mul→Add batch、18752个single调用；logical Mul662528 / Add664896。每phase的native lane计数与独立行/beat/K预算核对。724160读、27776写及ACK；chunk1对前一state累计132096读beat，最终state staging1024读beat。完整payload98304B（输出32768B、state65536B）均ACK。输出末ACK和最终state末ACK分别背压，确认不抢跑、不释放资源、不提前完成。成功staging回执仅退休一次，两个chunk均完成，但scratch/output/state均未发布，block commit及generation没有推进。

根执行1测试，0skip/failure/error，34.988秒unittest、35.106447783秒payload、exit0。1CPU、512MiB地址空间、110秒CPU、115秒alarm、外层GNU timeout120秒及TERM后2秒KILL。仅允许两次完全固定的只读Git source identity命令（原单次10秒timeout）；其余派生进程及网络禁止。1685个文件执行前后hash一致，复用原ELF，无编译/下载。不是另一个owned-process-group supervisor已运行的证明。

这是cold单head、合成原始输入的完整M128 GDN软件staging资格，不是全部head、包含投影/卷积/MLP的完整block、真实模型权重验收、Chisel/HardFloat/RTL或硬件性能验收。4418次exp无饱和仅说明本温和fixture未触发，未解决真实模型下exp饱和或UF策略问题。原Qwen2运行终态仍UNKNOWN，不重启、不继承丢失PASS。
