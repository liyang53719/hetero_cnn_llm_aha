# 原 v0 全 block 的 Dense＋矩形 Attention 软件映射

同一冻结C++ ELF、相同官方L0权重/embedding arena，从实际前级结果执行Dense、
RoPE、矩形QK、softmax、PV及后续O/残差/Norm/FFN。cold M16/M128全部15阶段
分别663552/5308416个FP32值逐字节等于封存v0；CPU用时4.00/27.05秒。

本增量仅将Attention真实数据移动纳入已有bank数值模型。QK保持16条j%16
独立FP32 FMA链，再按0..15顺序相加；softmax顺序与原expneg不变，PV按递增K。
实际数学没有改动，也没有将官方reference输入代入中间阶段。

M128下A/C使用168words/bank、B使用160words/bank，容量仍为16×1024×32B加
16×512×32B。五partial槽按条带批次复用，PV仅在QK排空后复用B；五accumulator、
两结果槽及一finalValue没有增加。每行在其causal最后有效K的真实返回值上捕获，
防止后续零概率FMA把负零变为正零。该捕获依赖返回tag，不能假称现有硬件有
逐行write-mask；相应路由仍标记未实现。

Attention实际数值循环记录19200 wide steps、25362432 useful MAC和29884416
active-slice executed MAC。软件指针解引用字节与模型operand gather字节分别
记录，不把二者当作真实端口事务；无硬件完整周期，利用率留空。原native BF16
阶段门/最终FP32预算FAIL保持，政策状态为DIAGNOSTIC_NOT_ACCEPTED。
具体而言，原M16的BF16阶段门PASS但最终FP32门FAIL；原M128两门均FAIL。

## 复验及来源

先遵循[已提交Dense证据与原基线生成步骤](../QWEN2_DENSE_RESIDENCY_NUMERIC_20261011/README.md)。
该历史文件及30个相同阶段hash固定在commit299949a03876fb561010afb6e1d83097db0ca593，
本SUMMARY包含其SHA，不复制全部旧计数或大张量。若仅有摘要而缺原始文件，不能
宣称旧实际输出已复验。

唯一差异是准备时显式启用矩形映射，随后execute自动检查冻结provenance：

```sh
python scripts/qwen2_dense_residency_numeric.py prepare --rectangular-attention --output work/rectangular-replay/generated
```

按原步骤依次执行M16、逐阶段字节比较、M128、逐阶段字节比较；生成目录及输出
目录改为`work/rectangular-replay`。不可跳过M16前置等价检查；同一sealed arena SHA
仍为`c34bcef98ca05d3c05087559741152082492b40fa6b74e072a1dec589c964a69`。
生成器需要上述历史commit的原C++对象，浅clone需先执行：

```sh
git fetch --no-tags --depth=1 origin 299949a03876fb561010afb6e1d83097db0ca593
```

13项合成小门包含M3/M17完整链、M1/M17/M128直接Attention、12Q/2KV几何、
条带消减、causal负零、pad溢出不污染已捕获结果、物理别名/哨兵/错误tag和
提早复用拒绝。它们不会下载真实权重。本轮实际M128只做一次，生成源码、ELF、
日志和全部实际输出保留于任务工作盘，不提交数据进Git。

仍未覆盖：carried prefill、Host/iDMA/ACK时序、硬件seed及重新分区、真实flags、
Chisel/RTL和原官方精度验收。资源图的29.701173%是旧乐观上界，未因软件数值
执行而变成预测或实测。
