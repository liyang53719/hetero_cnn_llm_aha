# Qwen2 冷预填充 Attention：固定资源矩形映射软件模型

本报告对应 `scripts/qwen2_rectangular_attention_model.py` 及其独立测试。
这是源码绑定的 pre-RTL 事件、布局和流量模型，不是已实现的 Attention owner，
不是周期仿真，也不构成性能或数值验收通过证据。本矩形映射的 Attention 自身
仅按 issue 几何即可排除 80%：M128 上界32.25%，M1024上界61.01190476%。
完整 block 仍需结合 Dense、其他 owner、DDR 等单独判断。
本模型仅覆盖已批准的 BF16 Matrix / FP32 累加；原数值门禁状态与阈值均不变，
边界位测试不代表验收语义已经改变。完整实际模型与多层门禁仍须单独通过。

## 几何、算术顺序与现有接口

只覆盖 Qwen2-1.5B 的 M128、M1024、batch=1、past=0、12 Q heads / 2 KV
heads、head dimension=128。Q head 0..5 读 KV head 0，6..11 读 KV head 1。
未添加 prefix cache、新 Matrix、SFU、SRAM、物理 accumulator context 或 SRAM 端口。

源码基线见脚本内 14 个 SHA256 pins；源码漂移时报告生成必须失败并重新审计。
主要约束来自 `Qwen2Block.scala`、`MatrixPipeline.scala`、`RetainedMatrix.scala`、
`QwenOwnerProtocol.scala`、`BurstProtocol.scala` 和 Dense SRAM / context scheduler。
数值依赖另绑定 `Protocol.scala` 的 BF16 RNE/finite、`BlockFloat.scala` 的
scalar/status规则、`EmitHeteroBF16Fma.scala`、`EmitHeteroFP32Alu.scala`，以及
保留的五context FMA lane和command endpoint RTL。拓扑pins不能替代这些数值依赖。

- QK 物理行对应 16 个 query，列对应最多 256 个 key，32 列为一个真实 slice。
  每个合法 query/key 对依然是 16 个 FP32 部分和：条带 s 按
  s、s+16、…、s+112 做 8 次 BF16×BF16→FP32 FMA。16 个结果从 +0 开始，
  按条带 0→15 做 FP32 add。不能替换为顺序 128 项 dot，测试含两者不同的反例。
- 因果有效性为 key≤query。QK 矩形仍执行无用乘法，但只归约、缩放、写入合法
  分数。不可把矩形内无效结果纳入 max/exp/sum，也不能用其非finite值拒绝合法输出。
- PV 物理行对应 query，128 列对应 head dimension；只启用前 4 个 slice。
  B 广播来自一个 KV head，A 广播为各 query 的 probability。现有共同 A 广播
  不能让后 128 列独立处理另一个概率不同的 head；没有声称满 256 列 PV。
- PV 仍按 key 递增累加。每行在返回 key=query 时捕获 FP32 最终值，此后该行的
  padding 结果丢弃。测试证明 +0 padding 可以把合法 -0 改成 +0，因此不能只等
  tile 最后一拍取所有行。每行捕获不关闭 context；最后一个 query 的最后 key
  才发送 `last/finish`。需要返回 key 的控制标签及按合法行检查返回值finite。
- Q/K/V 的当前 DDR 容器是 FP32，4 B/元素；进入片上存储时 RNE 到 BF16，
  2 B/元素。输出仍 FP32。位模式测试覆盖 BF16 ties-to-even、FP32 fused rounding、
  渐进下溢和 signed zero。附带FP16→FP32转换仅是泛用小工具测试，不参与映射，
  不作为新增方案或验收进展。
- score scale、exp 的既有 FP32 recipe、max 比较及递增 key 的 sum 顺序不变。
  相同 probability 的 FP32 multiply 在本候选中每 query/key 计算一次再复用，
  不再为 8 个 PV 列块重复；其 BF16 ingress rounding 不变。端到端 softmax
  数值验证不由本脚本重新实现，更不能用原生 exp 替代硬件 recipe。

Matrix 的错误语义与 Scalar 必须分开。`MatrixStreamResult.error` 是协议错误，
不携带 FP exception flags；endpoint 内部的 `mflags` 没有穿过这个接口。
现有 core 实际检查的是返回FP32值的 `finite`。候选只需在合法 QK 条带最终值、
PV row-final 值返回时检查，并在 context clear / 值捕获前完成：同一条累加链的
NaN/Inf 不会在后续有限操作数 FMA 中恢复finite。独立libm位模式测试覆盖有限
BF16乘积溢出到Inf及后续Inf/NaN传播；这不是RTL或flags通道验证。

`BlockScalarFloat` 的 legacy Add/Mul/Div 除非finite外还拒绝underflow等错误，
只有明确的 `MulIeeeRne` 例外；本Attention没有使用该例外。小合成函数仅比较
rounded bits，没有模拟Scalar exception/status返回。因此Matrix渐进下溢测试
不证明Scalar可接受；后续接共享Scalar必须保持错误返回。本模型沿用Scalar归约，
未实现或计入Vector化收益，也不能通过Vector化静默屏蔽既有错误策略。

## 原物理 bank 所有权与容量

Dense 原 A 组仍是 16×1376×32 B=704,512 B，B 组仍是
16×160×32 B=81,920 B。没有把 768 KiB 看作可自由改变深度的平坦池。
在 Dense owner、Matrix 和先前写 ACK 全部排空后，候选 Attention 独占借用它们。
当前接口尚无这种 lease、SRAM 访问与结果写回路由，需要实现后验证。

| A 组对象 | M128 | M1024 |
|---|---:|---:|
| 16 query ×128，BF16 | 4,096 B | 4,096 B |
| 一个 KV head 的完整 K，BF16 | 32,768 B | 262,144 B |
| 同一个 KV head 的完整 V，BF16 | 32,768 B | 262,144 B |
| 16 query 的 FP32 score | 8,192 B | 65,536 B |
| 16 query 的 FP32 probability 工作区 | 8,192 B | 65,536 B |
| A 使用合计 | 86,016 B | 659,456 B |

每个 tensor 行用 `bank=row%16`；同一行内每 32 B 一个 word，按对象分配
不同 base word，完整地址计算和跨对象不重叠已测试。K/V 保持 token-major，
因此不需要声称已实现免费的转置，但 QK 列聚合要付出实际 bank 读取。

一 context 模式在 B 组分配一份 16 KiB QK partial C。五 context 模式分配
五份，恰好 81,920 B。不是保存 16 份完整条带 C。PV 的行终值捕获在 QK
全部归约后复用 C 的第一槽，仅需其中 8 KiB。M1024 五 context 峰值使用
741,376 B；余下 45,056 B 全在 A 组，尚未用于任何免费缓存。

573,440 B core SRAM、12,288 B elementwise SRAM、8,192 B 原 score/prob
SRAM 均保留各自所有权，未挪用。5 组 accumulator、两项 MatrixResultFifo、
现有 operand FIFO 不计入 768 KiB 数据 SRAM，也未复制出新的寄存器缓冲。
新 gather/lease/标签/捕获/掩码/仲裁控制需要设计及面积记账，本报告没有证明其零成本。

## 事件闭包与五 context 轮转

`--contexts 1` 是保守单在途模式；`--contexts 5` 将 QK 的 16 条带分成
5/5/5/1 四组，每组使用 context 0..4。每轮为各 context 发一项，然后等待
各自返回，再发下一轮，故最多 5 项在途，不超过现有 8 项 metadata FIFO。
同 context 前一项未返回时不能再发。无任何周期或回授延迟假设。

每 context 的第一次 issue `clear=true`，第八次 `last=true`。组内最后关闭的
context 才带 `finish=true`，符合现有 seen/closed 协议。仅最后结果 emit。
返回结果经原两项 wide result FIFO 逐项搬入对应 B 槽；消费者同时处理一份，
FIFO 的物理容量仍为两份，不能把整个矩形结果额外寄存一遍。按条带次序归约后
才产生 `partial_release`，未释放的槽不能被下一组覆盖。组结束后才能重新 clear。

PV 单 context 单在途，因为当前只驻留一份 16 行 score/prob，而不是凭空给
5 个独立 query tiles 分配同样状态。后续若扩展 PV 五 context，应重新审计所有权、
score/prob 容量及最末行捕获，不能把 QK 的五 context 支持泛化为整个 Attention。

事件顺序为 owner acquire → KV load/ACK → query load → QK stripe groups →
ordered reduction → score scale / max / softmax → PV → row capture → output
write/ACK → 下一个 tile，最终排空并释放 owner。没有 FP32 accumulator seed；
QK 条带独立从零开始，PV 不 split-K，因而也不需要虚构 seed restore 端口。

## 流量与计数，不是周期

| 项目 | M128 | M1024 |
|---|---:|---:|
| 完整因果 QK+PV useful MAC | 25,362,432 | 1,612,185,600 |
| 已启用 slices 内 issued/executed MAC | 29,884,416 | 1,648,361,472 |
| QK wide issues | 12,288 | 245,760 |
| PV wide issues | 6,912 | 399,360 |
| 外部 Q/K/V FP32 读取+输出 FP32 写入 | 1,835,008 B | 14,680,064 B |
| QK K 32 B bank-word 读取 | 31,457,280 B | 1,660,944,384 B |

以上总流量是本 Attention 候选自己的 Q/K/V/输出，不是完整 decoder block 流量。
KV 每 head 从 DDR 读取一次，驻留后复用于 6 个 Q heads；query 每 head/tile
读取一次。所有片上 partial、score/prob 的读写仍在脚本中单独计数。

从 token-major K 提取一个 BF16 depth 元素，本模型读一个 32 B word，只有
2 B 是该次 payload。256-key列需要256次 bank-word读取，均匀跨16个bank
也至少分16批。Q 和 K、P 和 V 共用 A 组，事件串行处理冲突，没有再加端口。
本模型未利用跨条带 K word 的缓存；以后可在余下 A 容量内显式预留转置块，
但需加入加载、转置写入、再次读取、失效和端口占用，不能当作免费寄存器。

scalar score/prob 写使用保守的 32 B read-modify-write，不假设新增 byte enable；
partial 保存和 PV 行捕获以完整 word 搬运。FP32 归约和 softmax 请求数单独列出，
没有借用新 SFU，也没有将其与 Matrix/DDR 全部免费重叠。

`useful_fraction_of_executed` 只衡量已开启 slice 内的浪费，M1024约97.8%，
绝不等于4096资源周期利用率。脚本另列所有 issue 的4096容量槽和空闲slice槽。
每周期最多接受一次wide issue，故Attention自身有几何上界
`useful MAC / (4096 × wide issues)`：M128=32.25%，M1024=61.01190476%。
这已排除本映射Attention自身的80%，与1/5个context无关；增加context不能减少
这些必需wide issues。完整block是否达标不能由Attention上界独立决定。

本候选保守沿用现有Scalar：P为causal head/query/key对数，归约16P、QK缩放P、
softmax diff/exp/sum共3P、probability缩放P、每行倒数12M，至少
`21P+12M` 个Scalar请求。单请求口每周期至多接受一次，以下是下界/上界而非
SFU延迟假设；没有声称exp/div实际只需一拍。

| Attention条件界 | M128 | M1024 |
|---|---:|---:|
| 必需Scalar请求 | 2,082,048 | 132,261,888 |
| 即使Matrix完全重叠，Scalar单口给出的U上界 | 0.29739948% | 0.29759140% |
| 当前事件顺序Matrix/Scalar串行时周期下界 | 2,101,248 | 132,907,008 |
| 对应串行U上界 | 0.29468202% | 0.29614691% |

因此只把矩阵计算矩形化且保留Scalar归约，离80%仍很远。实际FMA回授、bank聚合、
RMW、命令/排空、DDR与写ACK等只会增加完整Attention周期。所有 predicted/measured
cycles/utilization字段仍为空；条件下界不能写成实测或周期预测，也没有推出完整
decoder block的总周期或利用率。

## 可复现检查

运行：

```sh
python scripts/qwen2_rectangular_attention_model.py --tokens 128 --contexts 1
python scripts/qwen2_rectangular_attention_model.py --tokens 1024 --contexts 5
python scripts/qwen2_rectangular_attention_model.py --tokens 1024 --contexts 5 --out /tmp/qwen2-attention/m1024.json
python -m pytest -q tests/test_qwen2_rectangular_attention_model.py
```

`--out <path>` 自动建立父目录并写出严格JSON（`allow_nan=False`）；默认仍向stdout
输出。`--events-jsonl <path>` 可导出依赖事件，ordinal只是事件序号，不是时钟拍。
M1024完整trace较大；常规输出无需生成。测试覆盖完整 M128/M1024 因果迭代域，
GQA路由、bank地址/容量、不覆盖活C、context协议、行末捕获、M128聚合与显式
事件一致、原16条带算术顺序，并以独立 libm `fmaf` 对照固定位/随机有限样本。
只用了小型独立合成数组，没有实际权重、Chisel生成、RTL或EDA。
