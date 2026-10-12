# 三模型五个完整 block：先验证模型与 prefill

2026-10-11 起的执行顺序是 Qwen2-1.5B layer0，然后 Qwen3.5-0.8B
layer0 / layer3，再到 Qwen3.5-35B-A3B layer0 / layer3。先用同一批真实输入
在软件模型中验证完整 128-token prefill，再进行更长输入和冻结激励的硬件回放。
M16 只作早期诊断，不代替 M128；逐次 M1 launch 不称为一次 prefill chunk。

## 已有证据及边界

| 完整 block | 已有实际范围 | 尚缺的主要闭环 |
|---|---|---|
| Qwen2-1.5B L0 | 固定官方权重/embedding 的 cold M16、M128，公开21命令同一软件实例贯通15主阶段，对独立v0算术逐位相同；M128原比较超时与后处理PASS分别保留 | 完整29诊断节点及官方BF16/FP32数值门仍未通过；真实carried prefill与M128完整硬件待验 |
| Qwen3.5-0.8B L0 GDN | 79bbe 的同 DUT cold M1→carried M1，完整 RMS/核心/O/残差/FFN/双状态 fence；canonical 和原 native 数值门通过 | M128；整链 fault/reset/restore；完整周期计数 |
| Qwen3.5-0.8B L3 Attention | 98c7 的完整双 M1 canonical 通过；后续保全 49 个真实 tensor 的相同输入官方 terminal/final/KV 比较通过 | 实际内部 GQA 33–37 未导出；输入 RMS 归约差异的生产修复；M128 |
| Qwen3.5-35B-A3B L0 GDN+MoE | 固定官方配置、forward、权重 header 和 E0 几何/算子合同 | 真实权重和输入、路由/专家执行、完整数值模型及硬件 |
| Qwen3.5-35B-A3B L3 Attention+MoE | 同上 | 同上，含完整前缀 Attention 与 MoE |

这些记录分别绑定原源码和输入，不能因重建工作区而继承到新文件。
GDN 证据见 [79bbe 回执](U00_2_HOST_GDN_BLOCK_CI_79BBE_20261010_CN.md)，
Attention 证据见 [98c7 回执](U00_2_HOST_ATTENTION_BLOCK_CI_98C7_20261010_CN.md)。
三模型完整 native 精度合同、M128 与 PPA/利用率大项仍开放。

## 当前 MAC 数据

0.8B L3 的原双 M1 回执记录 6,215,798 个完整 launch 周期、36,712,448 useful
MAC、589,398,016 executed MAC。固定资源是 4096 MAC/cycle，因此整时段
useful 利用率为 0.1441970926%。分母包含全部 descriptor、DMA、Scalar、等待和
末写 ACK。此数据来自单 outstanding、随机 1–7 拍延迟和背压的验证内存服务，
不能外推真实 DDR 或 M128 性能。Dense 命令占两个 launch 周期的约 85%，
其中也包含内存等待，不能把这个比例解释为纯计算时间。

0.8B L0 每次实际 useful MAC 是 21,528,576；原回执缺完整 launch 周期与
executed 计数，利用率留空。Qwen2 已有 M16 的 749,101,056 MAC 和
83,428,956 周期来自合成权重 16-lane 功能后端；不是官方工作量，也不是
Matrix4096 的测量。35B 两个 block 尚无完整硬件计数。

本轮在模型与硬件描述阶段同时检查有效 MAC、固定资源、实际形状映射和流量
约束，评估至少 80%、理想 90% 的目标。逻辑 MAC 计数、乐观上界、周期预测和
RTL 实测分开记录；没有完整周期模型就不填预测利用率，不改变现有数值门限。

## Qwen2 当前执行门

1. 固定模型 `ba1cf1846d7df0a0591d6c00649f57e798519da8`，固定官方
   Transformers `9fe3f585bb4ea29f209dc705d269fbe292e1128f`。仅获取 L0 的
   12 个 BF16 tensor（93,595,648 B）及 embedding 0–255 行（786,432 B）。
   分段 Range、HTTP 206、源 header、shape、原地址与每段哈希都核验。
2. 以原官方完整 DecoderLayer 和独立完整公式逐阶段比较。FP32 数学结构、
   native BF16、硬件固定顺序三种模型分别记录，禁止以一种自比通过替代另一种。
3. 从已有 C++ canonical 的原数学函数生成普通 CPU 软件模型，执行完整
   15 阶段、递增 K FMA、BF16 RNE、既有 exp 近似与 FP32 残差。该步骤不生成
   RTL，也不是直接执行 Chisel，更不证明 Host 调度和 DMA 已通过。
4. 常规 M128 验收要求对应 M16 全部先过；另允许明确不验收的有界 M128 诊断，保留前置失败并返回退出码 1。M128 逻辑工作量是
   6,014,828,544 MAC、5,308,416 个阶段 FP32 值。结果及源码/输入身份封存后
   才选择必要的最小 Chisel/RTL 回放。

本轮真实模型结果已经取得，均未生成 RTL：

- 固定 L0 与 embedding 的 94,382,080 B 已由 22 次严格范围请求获取并核验。
- 单独 cold M16 的官方 BF16 与独立模型全部 29 个节点在既有门限内，作为
  cold M128 的完整前置回执，包含全部输入、输出文件与重算门限核验。
- cold M128 完整模型已执行；scores / logits / probability / gate 超原 operator
  门，最大差分别为 16、8、0.031494140625、0.041015625。末输出最大差
  0.015625、平均差约 3.86e-5，在原末输出门内。完整阶段门仍是 FAIL。
- 同样保留了 cold16→carried16 的独立失败：单个有效 score/logit 差 0.25，
  末输出仍在限内。carried M128 尚未执行。
- 两个失败中的 input RMS 与 RoPE 系数均逐位一致。M128 最大 score 差属于
  因果 mask 遮住的未来位置；输入 Q/K 相同，但不同点积归约在 BF16 中点两侧
  舍入。有效 logit、probability 和 gate 的差异则可追至少数 Q 投影的舍入。
  FP64 及不同 FP32 FMA 顺序仅作诊断，未替换参考、未提高门限。
- 原 Chisel 对应的 C++ 软件 recipe M16 已执行全部 15 阶段；对独立 FP32
  的末输出 relative-L2 约 0.01662、cosine 约 0.999862，未过既有开发预算。
  这是现硬件算术的模型差距；不等同于新 RTL 结果。
- 显式 M128 recipe 诊断已完成全部 15 阶段及 5,308,416 个输出值，耗时
  29.988 秒。FP32 末输出 relative-L2 约 0.033236、cosine 约 0.99944754，
  状态为 DIAGNOSTIC_NOT_ACCEPTED、退出码 1，未绕过 M16 失败。相同 Q/K/V
  下的独立消融中，FP32 Attention 的 relative-L2 为 0.001603；只加入 Q/K
  的 BF16 入口舍入即变成 0.039161，再加入 probability/V 的 BF16 为
  0.039204。说明入口量化是本样本主要误差来源，未更改硬件精度或参考。
- 两种官方 dtype 自身的差异也单独检查：原 DecoderLayer 在没有 hook/tracer
  的独立重放中，对 BF16、FP32 各 196,608 个末输出均复现原回执全部位；
  同一 BF16 权重/embedding 的无损展开、eval/noautocast、eager、positions、
  因果 mask 与空 cache 都已核对。官方 BF16 对官方 FP32 的末输出 relative-L2
  为 0.259512、最大差 1.050279。head6/query93 的 94 个有效 BF16 logits
  全舍入为 4672，softmax 约为 1/94；FP32 的 self/次高 logits 分别为
  4699.44385/4688.33984，self 概率 0.9999845。这一差距在官方同源两种
  dtype 中也可复现，不能简单当作硬件缺陷，也不能因此改变既有验收门限。

完整数值/身份摘要见 [本轮报告](../reports/execution/QWEN2_PREFILL_MODEL_20261011/)。
这些不同模型的失败分别保留，不能将末输出通过改写成全部 producer 通过。

已经查到的 Qwen2 packer 缺陷是坐标不一致：当前 Chisel 和 canonical RoPE
使用 split-half，而 stack packer 仍将 Q/K 权重和 bias 变成 adjacent 布局。
修复必须保留官方 split-half 排列并版本化 pack 合同；旧包不能静默重新解释。

## Prefill 来源与限制

官方模型的 prefill 能力与本仓库当前 Host adapter 的验收范围是两件事。
现有 Qwen2 完整 Chisel 路径本来支持 `maxTokens <= 1024` 和 16-token
权重复用。0.8B 完整 Attention Host 的单行限制及 GDN InputPrep/recurrent 的
单 token 限制是在本项目新接线时增加的，不能称为上游模型或阵列架构限制。
应先复用已有多 token 路径，再逐项扩展必要的 adapter、状态和完整事务门禁。

Git 来源进一步区分了资源与接线：Qwen2 1024-token 路径始于 `7909848a`，
16-token 复用始于 `3ec898b1`，retained512/iDMA 始于 `9c5ac94f`，八切片
4096-MAC 阵列始于 `c490193c`。GDN 单 token core 限制始于 `904dccf2`，
完整 block 继承于 `da1cd9c9`；Attention 完整 block 单行限制始于 `675d0ccf`。
当前 Host 绑定本项目 Revision8B-B Matrix、HardFloat 包装和 pulp iDMA，
并未实例化完整 AHA/Garnet sidecar。上游来源 pin 本身不能替代本项目整链验收。

## Prefill 流量条件界

`scripts/qwen2_prefill_traffic_bound.py` 将以下算式绑定到实际源码 SHA，
不是全周期仿真器。当前 768 KiB Dense scratch 中 A 为 704,512 B、双 B 缓冲
为 81,920 B；A 使用 BF16 存储。K1536 的 80 行只用 245,760 B，但受到五个
accumulator context 的限制；K8960 的 32 行用 573,440 B，受每 bank stride
与容量限制。当前换 row group 会重读权重，没有隐含全权重驻留。

| 输入及权重格式 | 单 Dense 权重入口流量 | 仅权重读周期下界 | 全 block useful 利用率上界 |
|---|---:|---:|---:|
| M128 / BF16 | 242,221,056 B | 3,784,704 | 38.79997% |
| M128 / FP32 | 484,442,112 B | 7,569,408 | 19.39998% |
| M1024 / BF16 | 1,739,587,584 B | 27,181,056 | 44.4860% |

假设单 64 B/cycle R 口无空泡、计算与读取理想重叠，且忽略激活/参数读、
全部写回、Scalar 与依赖间隙，实际只能更低。M1024 这里只是条件界，未执行
M1024 数值模型。当前调度下 M128 权重流量已经排除 80–90%；不能只增加
token 数就宣称达标。后续先分析固定 MAC/SFU 下的驻留、FP32 partial 保存和
分块调度代价；任何新增状态或读写并发必须透明记账，不能当成免费的优化。

## 工作区恢复与待办

从已验证远端 `c14deb7779a47044762bccdd9d8a95abd3b24683` 建立独立 checkout。
原未发布 48 文件候选不再可见，不能恢复其旧 PASS。已重新获取并验证旧真实
replay ZIP 和 ELF/SV 构建包的原 GitHub digest；不会以重新 fresh 的输入冒充旧输入。

重新实现的 RMS 小模型已在 Torch 2.10.0+cpu DEFAULT 和 AVX2 对两个保存的
真实输入通过官方 RMS 节点与 BF16 输出逐位比较；carried 的 304/542 两个 lane
被修正。辅助 `torch.sqrt` 存在 1 FP32 ULP 差异，官方实际调用的是 `rsqrt`；
这个诊断被保留。新 Scala 与 GQA 观测代码尚未执行新 RTL，随 Qwen2 优先级后置。

- done（局部）：Qwen2 官方 L0 payload 获取与身份核验、完整 cold M128 软件执行、独立官方重放及失败定位。
- ongoing：Qwen2 精度合同逐节点对齐、M128 原门限失败修复、恢复源码及证据。
- to do：Qwen2 同输入完整硬件、0.8B 的 M128 与 RMS/GQA 实际修复验证、35B 两个完整 block。
- 保持：U00.2 ongoing、U01 to do、C02.2 OPEN。以上局部进展不关闭跨模型大项。

## 后续显式模型策略

首批 `5ca2b5c` 已核验远端 tree/31 个 blob，三项轻 CI 全部通过，模型合同
CI 实跑 83 项测试。完整 native 精度失败仍开放。进一步的
[官方 BF16 物化候选](QWEN2_BF16_POLICY_DIAGNOSTIC_20261011_CN.md)和
[固定资源驻留/调度审计](QWEN2_PREFILL_RESIDENCY_AUDIT_20261011_CN.md)
分别保留数值和资源边界，均未生成新 RTL。

## 固定资源矩形 Attention 模型增量

`b7e24cc` 的 94 项模型合同 CI 已通过，四份流量/Host 下界报告均与本地
逐字节相同。数值候选仍保留 M128 producer FAIL，完整 block 尚未验收。

[矩形 Attention 候选](QWEN2_RECTANGULAR_ATTENTION_MODEL_20261011_CN.md)
现给出 M128/M1024 的 bank 布局、1/5 context 事件和完整片上/外部流量，
不生成 RTL。33 项新轻量检查涵盖舍入顺序、因果/GQA、row-final 捕获、
资源与14个源码pin；与既有11项bound测试合计44项通过。该候选尚未接
生产 owner。Attention自身issue几何上界为32.25%/61.0119%，若保持
单Scalar归约与softmax，乐观上界更低；全层80%目标仍需驻留和共享
Vector/SFU调度证明。Q21.3/U00.2保持ongoing，U01保持todo。


## 真实 carried M128 与共享资源模型增量

`01cd1bf` 的 127 项轻量模型 CI 已通过，八份源码绑定报告均与本地逐字节
一致。新一轮先复用封存 cold 的实际 K/V 输出，再以绝对位置 M..2M-1
执行 carried M16、M128。不是逐 token 循环，也没有注入官方 cache；cold
与 carried 是不同软件进程，尚未验证生产 Host 的命令、DMA 和物理状态。

[carried 诊断](QWEN2_CARRIED_PREFILL_MODEL_20261011_CN.md)保留四种比较：
官方/独立各自 cache 的完整链，以及分别以实际候选旧 cache 为条件的参考。
M16 两条官方参考的已定义节点门通过；M128 四法均有 15 个中间节点失败。
M128 末输出最大差 0.0390625 在原末输出门内，不能覆盖 Q、Attention 和 FFN
内部失败。全部 14 项数据语义检查通过，原策略与 `NOT_ACCEPTED` 保持。
FP32 softmax 内部值没有已批准逐元素门，只检查原有行和等语义。

[共享资源预约模型](QWEN2_PREFILL_RESOURCE_SCHEDULE_20261011_CN.md)覆盖19个
owner、21个公开阶段的依赖、缓冲和最终 ACK。cold M128/M1024 的有用 MAC 和
Dense 权重读字节与已发布算式相符。默认时延未绑定，合成时延仅用于检查
预约器自身；可信全周期预测、Chisel 状态机执行和硬件死锁证明仍未完成。

[固定16路 SFU 候选](QWEN2_SHARED_SFU_SCHEDULE_MODEL_20261011_CN.md)保留
原 exp7/RNE 节点，建模1/2个向量 context 的 ALU、divider、回写和背压。
它需要明确的新控制状态和路由，尚未接 Chisel。既有 wrapper 在本次实际
M128 gate 输入全属非饱和分支，仅 SiLU 就至少2,723,839拍；这是绑定当前
实现的下界，不能当成新候选或任意16路 SFU 的极限。原硬件计数与上述
软件预约时钟分别记录，固定4096 MAC分母不变。

- done（局部）：sealed cold 实际 cache 的 M16/M128 carried 软件执行、四法比较与证据核验。
- ongoing：RMS归约和RoPE表精度首差诊断；完整producer门仍失败。
- ongoing：完整DAG资源预约与固定16路SFU调度的软件模型、未绑定时延清单。
- to do：明确数值政策后才做最小Chisel接入；绑定实际端口与FSM时延，最后冻结刺激跑RTL。
- 保持：Q21.3/U00.2 ongoing、U01 to do、C02.2 OPEN；不将末输出门通过写成完整数值通过。

## RMS1536 / RoPE 定点复现与后续整链诊断

`a17ebcc91cd3ffdd38e42743aa3264ea25d75f0c` 的模型 CI 实跑 168 项测试
通过，payload guard 通过，14 份报告的源 pins 均已复核。13 份报告逐字节
一致；资源合成报告的 4 个集合列表顺序不同，原失败保留。排序修正只规范
序列化，不改变周期/资源成员，并新增两个 Python hashseed 的回归。

[RMS / RoPE 单算子诊断](QWEN2_RMS_ROPE_POLICY_DIAGNOSTIC_20261011_CN.md)
覆盖旧 cold/carried M16/M128 的 20 组、1440 行评估。1536-channel 显式归约
使用固定 V8 / 四余数组 / 三块各16项的顺序，均值执行 FP32 除1536；随后
sqrt、reciprocal 和两个 BF16 物化边界均按冻结官方 CPU 源码。所有相同输入
RMS 观察节点及输出逐位一致。普通 C 和独立整数中点 RNE 核验通过。

FP32 powf/频率/角度/sinf/cosf 生成的位置 0..255 表在 BF16 物化后全部匹配
官方；FP32 中间值仍有差异，未证明任意位置或跨 backend 等价。这些结果
仅对实际源/运行时/输入身份有效，不以 CPU 名称代替 dispatch 验证。

旧 carried M128 actual residual 送入新 RMS 后，n1 相对完整官方链仍有
13245 个元素不同，max_abs=0.12353515625。这个反例保留，证明单算子同输入
一致不足以关闭整链。下一步是[隔离 v2 软件候选](QWEN2_RMS_ROPE_PREFILL_CANDIDATE_20261011_CN.md)
以同一新 ELF 真正执行 cold→carried，读取实际前次 K/V，再比较全部29节点。
该候选的数值 PASS/FAIL 与政策接受分开；始终 `DIAGNOSTIC_NOT_ACCEPTED`，
不改变原 v0 硬件、producer 门限或批准状态。

- done（局部）：20组 RMS/有界 RoPE 的独立数值及来源审查；CI 资源列表差异定位。
- ongoing：同新二进制 cold/carried M16→M128 整链诊断及首差分析。
- ongoing：固定资源性能模型，时延仍未完全绑定，尚无可信完整 Chisel 周期预测。
- to do：数值政策确认后最小 Chisel 接入及冻结刺激的完整 RTL 验收。
- 保持：Q21.3/U00.2 ongoing、U01 to do、C02.2 OPEN。

本轮 v2 cold128→carried128 已完成实际软件数值执行，分别30.55/33.11秒，
同一新 ELF 与 M16 一致。carried 从本轮新 cold 的实际 K/V 文件续算，没有
使用旧候选或官方 cache 替代。四种比较的失败节点数均由15降至4，末输出
最大差由0.0390625降至0.0078125，各法末门通过。

完整原门仍失败：cold 官方 scores/logits 最大差16/8；carried 官方两法
剩 scores/logits（max1）、n1（0.0625）、gate（0.0390625），独立两法
剩 scores/logits（max8）、q（0.125）、gate（0.0390625）。n1 的官方整链
差异来自其实际 residual 输入已经不同；相同实际输入的前/后 RMS 八节点
及输出全部精确。这是明确的数值改进和剩余边界，不能写成完整block通过。

首次 M16 新参考加载器漏了 Q/K token-major 逆布局，导致错误比较。原失败
和当时未发布源码快照已保留；补逆变换及非均匀 token/head 回归后重验，
新旧两次 M16 的实际 raw 输出及 ELF 逐字节一致。修正不更改候选算术。

逐执行拓扑的只读差异汇总进一步表明：所有新比较方法的第一处 bit 差均在
`qr` 投影输出，旧 v1 carried 的第一差在 `n0`。carried 官方首个超门节点
现在为 scores，独立参考首个超门节点为旋转后的 q；旧四法均从 qr 开始超门。
这些差异使用已保存全量数组复算，未注入官方中间结果或追加实际执行。
本批完整轻量模型合同198项测试通过（21.07秒），新精确提交的CI另行跟踪。

## e327e14 的终态与数值决策边界

`e327e14e549921e7569792bf6593fb0dea4b2397` 已发布并核对完整52文件tree。
该精确SHA的轻量模型CI实跑198项测试通过（30.33秒），payload guard通过；
下载的103634B紧凑artifact经SHA核验，14份报告全部逐字节一致。
这项CI没有重跑实际M128整链，也没有运行Chisel/RTL。

[BF16数值决策材料](QWEN2_BF16_NUMERICAL_DECISION_20261011_CN.md)区分了
Q投影舍入传播与相同Q/K的归约差异。完整形状官方QK重放复现393216个分数；
其中53与52.75的反例相差一个BF16 ULP，超过原绝对max门8倍。
该观察没有授权修改数值合同，也没有将原native FAIL改成PASS。

- done（局部）：新同ELF的M16/M128软件cold→carried、同输入RMS检查、全部29节点诊断及独立审查。
- done（局部）：52文件远端身份、198项轻量CI、14份紧凑报告复核。
- ongoing：原数值门仍失败；既有硬件算术与官方物化/质量门的版本化选择等待明确决定。
- done（局部）：现有固定16路SFU模型的HardFloat逐请求时序绑定与小调度回归。
- ongoing：完整DAG时序、自然flags及RTL校准；实际完整周期仍未绑定。
- to do：决定后最小Chisel接入；模型prefill闭合后才冻结刺激执行RTL。
- 保持：Q21.3/U00.2 ongoing，U01 to do，C02.2 OPEN。

## 8ac4849 已验终态及D14模型增量

`8ac48497c6fb6fa4e46db3593d4bf86174a05255` 的轻量CI实跑229项测试通过
（17.84秒），payload guard通过。172577B工件的SHA核验通过，17份紧凑
报告与本地冻结报告逐字节一致。没有重跑M128数值或运行RTL。

后续D14只加入显式软件选项，当前硬件仍为原options0。正常域整数递推与
独立有理数RNE/NX量化器对照，58项专项通过；本次完整轻量模型集244项
通过（22.76秒）。完整flags、组合电路面积/关键路径、硬件等价均未验。
原v0分支审计和失败身份不变，原数值政策/验收选择仍待决定。

完整资源界采用[版本化替换](QWEN2_PREFILL_RESOURCE_SCHEDULE_20261011_CN.md)：
保存输入分支条件下，当前Host上界由较松16.08848%收紧到11.11363%；这是
下界公式收紧，不是性能退化实测。即使仅改成D14原wrapper也只有11.88749%
上界，不能靠局部SFU候选关闭80%目标。

- done（局部）：8ac精确源码、229项CI、17份报告核验。
- done（局部）：D14正常域软件递推/拒绝边界及244项轻量回归；新提交CI另验。
- ongoing：原M128完整数值门FAIL与明确数值政策决定。
- ongoing：既有完整DAG的驻留/外部流量、单Scalar归约及端口所有权模型。
- to do：源绑定可行完整周期预测、政策明确后的Chisel接入与最终冻结刺激RTL。
- 保持：Q21.3/U00.2 ongoing，U01 to do，C02.2 OPEN。

## f103d32 终态与完整DAG驻留候选

`f103d32035204bf1bee9ccf5947e93afbcd13847` 的模型CI实跑244项通过
（31.59秒），payload guard通过；212870B工件SHA为
`389705975ed8620ac48b38f912f4dcb3d7e3f1a7d9b57124cf829b10b1f63961`，
20份报告与本地逐字节一致，源码pins对该精确提交核验。

下一增量已从局部SFU回到同一完整DAG：显式resident_m128_nc3方案将down
A六遍读取降到两遍，并保留原五contexts、FP32 accumulator prefix和全部
最终ACK。全19-owner/21阶段软件事件图的有用MAC计数完整，Dense驻留容量
和Attention高水位兼容；M1024在此分区超容量而明确拒绝。

该候选的完整外部流量及Scalar请求仍分别要求至少2355200、2476288拍；
按owner依赖求和的宽松下界4944128拍、利用率上界29.701173%。下界还没计
真实SFU、bank、partial路由、DDR等待，不能写成达到80%或预测周期。
没有增加算术实例或改精度；SRAM分区、seed、路由和控制均仍是未实现候选。

独立审查先发现seed可省略、逻辑行可越界、store/ACK可提前三类模型缺口，
均加入显式shape/物理地址/seed/K进度/capture/sink关联及负例后复核关闭。
这仅约束成功路径的软件事件图，不替代硬件故障恢复、完整数值或死锁证明。
本批完整轻量模型集248项通过（24.17秒），21份紧凑报告已生成；新精确提交
的CI需发布后另行核验，没有追加完整权重数值或RTL运行。

- done（局部）：f103精确tree、244项CI及20报告核验。
- done（局部）：M128驻留方案的全DAG计数、容量/租约/前缀/ACK小门及独立审查。
- ongoing：原数值策略决定及完整M128 native门FAIL；没有降低阈值。
- ongoing：全DAG的实际端口服务/所有权绑定，关注外部流量与Scalar归约。
- to do：有证据的FP32源复用/转发接口、flags/时序与最终Chisel/RTL闭环。
- 保持：Q21.3/U00.2 ongoing，U01 to do，C02.2 OPEN。


原 v0 cold128 保存 gate 已追加分支核验，不依赖未批准的 v2。
1146880次reciprocal全部落入原HardFloat的D26分支；绑定后原wrapper算术
边沿差下界4515839，同16divider即使理想调度也至少1863680拍。
对该cold128输入，仅后者的全层4096分母利用率上界78.793784%；
这个条件上界不适用于所有长度/prefix，且未计入其他开销。

同一SFU候选模型已实现逐请求D25/D26时序与同拍返回/新接收；默认unbound
及原合成模式保留。资源整层报告只引用来源公式，21类宏参数仍未绑定。
本增量专项57测试及完整模型集229测试通过（21.14秒）；第一次本地完整
测试缺PYTHONPATH导致collection错误，修正到与CI相同环境后通过，失败日志保留。
本批新精确SHA的CI需发布后另验，不以本地结果代替。

## ebd3b89 终态及真实驻留数值门

`ebd3b897dcb08be2ad773b936da5ec6fb921d932` 已完成248项轻量CI（27.13秒）
和payload guard；227784B工件SHA为
`4184ae52214b9bc16111c21641cacaea1b7bb3a5d90dbae8820adc75b069d220`，
21份报告逐字节等于本地结果，各源码pin对该精确提交复核。

随后将驻留方案落实为原C++ recipe中的真实bank读写，沿相同BF16输入/权重、
逐K FP32 FMA及最终偏置顺序完成M16和M128，15阶段分别663552/5308416值
全部逐字节等于封存v0。先核原arena/权重/源码/输出身份，再M16验真后才执行
M128；同一ELF、同一只读arena，没有预装中间golden。M128软件耗时24.94秒。
独立审查复核全部30个输出文件、源码及7 Dense计数，无需重复forward。
完整身份与复现入口见[紧凑证据](../reports/execution/QWEN2_DENSE_RESIDENCY_NUMERIC_20261011/README.md)。

本门只证明软件驻留映射保留v0数学结果；原M128官方BF16阶段门与最终FP32门
仍失败，状态是DIAGNOSTIC_NOT_ACCEPTED。不是Chisel执行或21命令Host回放，
没有验证seed硬件、iDMA/ACK、完整flags或时序；本次也没有carried prefill。
CPU运行时间不能换算为MAC利用率。新8项合成数值/控制测试并入轻量CI，精确
新提交的CI在发布后另验，真实权重数据不入Git或该CI工件。

- done（局部）：ebd精确tree、248项CI及21份报告核验。
- done（局部）：实际M16/M128 cold驻留软件数值与v0逐字节等价、独立复核。
- ongoing：原M128 native数值FAIL及明确数值政策决定，阈值未改变。
- ongoing：完整DAG端口服务、FP32 seed及bank生命周期与源控制实现对应。
- to do：可行全周期预测、政策明确后的最小Chisel接入与最终冻结激励RTL。
- 保持：Q21.3/U00.2 ongoing，U01 to do，C02.2 OPEN。

## 299949a 终态及同一全 block 的矩形 Attention 数值映射

`299949a03876fb561010afb6e1d83097db0ca593` 的轻量CI已实跑8＋248＝256项
通过，payload guard成功。227784B工件SHA为
`3898a0d31c5d5faf55ea7d7284cf4caa9c4c1bb115b292eab65b7161ab4ed2d5`，
21份报告与本地逐字节相等，源码pins对精确提交核验。

后续显式矩形模式将同一模型的Attention落实为真实bank读写与返回捕获，保持
原16条QK累加链、顺序归约/softmax和PV递增K。固定输入下M16先验真，再一次
M128完成全部15阶段；5308416值全bit等于原v0，CPU27.05秒。Attention的
19200wide/25362432useful/29884416 active-slice executed计数与事件模型一致。
没有完整硬件周期，因此不能换算MAC利用率。

新增验证暴露出需要明确的路由合同：每行必须在causal最后有效K返回时捕获，
后续零概率FMA可把-0改为+0。软件在实际B地址保存原返回值，未添加私有数值槽，
也没有假设现有硬件提供row write-mask。13项合成小门及独立源码审查通过；
[来源与复现](../reports/execution/QWEN2_RECTANGULAR_NUMERIC_20261011/README.md)
保留原native/最终FP32 FAIL和DIAGNOSTIC_NOT_ACCEPTED。

- done（局部）：299949a精确身份、256项CI与21报告核验。
- done（局部）：同一Dense＋矩形Attention数值链的cold M16/M128保序等价。
- ongoing：原官方数值政策决定与完整阶段门FAIL，未降低阈值。
- ongoing：与实际Chisel对齐的seed、bank路由、causal返回捕获及完整端口时序。
- to do：carried/更长prefill与冻结激励的最终硬件验收。
- 保持：Q21.3/U00.2 ongoing，U01 to do，C02.2 OPEN。

## 43440d 终态与最小 Chisel 接口候选

`43440dbad48c8e8af3112c1ae658db3ae64d76eb` 已完成13＋248＝261项轻量CI，
payload guard成功；工件SHA为
`9645af24197c1b5b2aae6479a25b64951f2913110ab5506001a3a1854f37579f`。
21份报告与本地逐字相同，源码pins按精确提交复核。

已将驻留数值模型的两个直接依赖落实为[可应用源码候选](../candidates/qwen2_resident_matrix/README.md)：
原 Matrix service 的可选 return tag，以及 begin/beat/commit/ACK 的 seed FSM。
Scala2.13.16/Chisel6.7.0实际编译和CHIRRTL前端检查通过；原FIFO/service与tag
default0的结构逐字相同（仅去来源位置），width1/16/32和非法宽度检查通过。
Seed源码可展开，但未接生产owner/五bank写口，不能称seed生产模式已通过。

45项小门包含13队列、25控制/地址和7runner负测。审查先修复reply背压下单拍
abort可漏锁存、失败lease复活及stale generation三类候选问题；修正后的模型
反例通过。前端比较器也修复字符串内`@[...]`被误删的风险，对同一已有IR
重新严格比较通过，未重复构建。证据见
[紧凑摘要](../reports/execution/QWEN2_MATRIX_INTERFACE_FRONTEND_20261011/SUMMARY.json)。

这是Chisel编译/展开结构门，没有生成SystemVerilog、运行Verilator或执行FPU，
不替代时序协议和完整block验收。原M128 native FAIL、政策待定保持；新精确SHA
的单项前端CI发布后另验，现行生产源码和旧回归入口不变。

- done（局部）：43440d的261测试/21报告身份核验。
- done（局部）：最小返回tag/seed源码、45个模型/身份负测及真实Chisel前端门。
- ongoing：原native数值FAIL；生产seed/bank-valid/ICG/owner实接与完整端口调度。
- to do：同资源真实小接口协议门、carried/长prefill及最终冻结激励硬件验收。
- 保持：Q21.3/U00.2 ongoing，U01 to do，C02.2 OPEN。

## 9f96b03 终态与真实 resident bank 读源

`9f96b038aaf5f67423bc64111a37467afd280d25` 的45项小门与6条实际Scala/CHIRRTL
命令均在CI完成，payload guard成功。978930B工件SHA为
`2547c7e086b976278e31b38f04386f1378a91a7645a02e648169ed1aa4f0899c`；
18份CHIRRTL与本地除源位置外逐字一致，87个官方Maven依赖SHA及来源manifest复核。

后续[真实同步bank读源](../candidates/qwen2_resident_matrix/RESIDENT_READER_CN.md)
已接到既有seed controller的前端组合；生产StreamingDense的默认关闭补丁使用
原aBanks.read、实际pending/FIFO/DMA/write排空条件。5条新增编译/展开命令通过，
默认大/小配置除源位置外逐字相同，enabled普通/burst及小深度拒绝展开通过。
21项模型和8项新增runner负测通过；独立审查补齐11-bit地址、最小物理深度、
迟到ACK和每bank端口检查。首次比较的assert源行号差异与修正过程如实保留。

reader/controller组合声明864bit状态和缓冲，使用16个单读单写256-bit bank。
每个有效512-bit restore需两次同bank读，但完整source FSM占4拍；M128原方案
仅restore路径就有5,111,808拍，未计其他阶段或停顿。旧29.70%宽松事件界不因此
成为可行预测。下一步先比较同固定资源的转置/驻留映射，再决定生产调度。

- done（局部）：9f精确CI/工件/源码/18份IR核验。
- done（局部）：真实bank读源源码、默认关闭生产读口补丁及模型/Chisel前端门。
- ongoing：完整owner metadata/lease/C保存、leaf seed/ICG及group-done发布接线。
- ongoing：原M128 native FAIL与数值政策决定，未改变算术、阈值或验收语义。
- to do：固定资源下转置映射实值/端口/全DAG流量比较，再选实际生产接线方案。
- to do：可行全周期预测、carried/更长prefill及冻结激励最终硬件验收。
- 保持：Q21.3/U00.2 ongoing，U01 to do，C02.2 OPEN。

## f28f7a5 终态与转置映射的完整 cold M128 数值

`f28f7a5fa6b45b820b18e972090190c84303e693` 的74项小门、11条真实Scala/CHIRRTL
命令及payload guard均在CI通过。工件9,782,822B，SHA为
`3f507aa8530d605cd5353685cee408c3d21640758b5c573aa0f9bb114239519f`；
27份CHIRRTL与本地除严格限定来源位置外相同，87依赖与两套源码manifest复核。

随后按原v0算术完成同一block的转置Dense＋矩形Attention cold M16/M128模型。
原A688/B80KiB、4096FMA和5contexts保持；先M16全663552值通过，再M128全
5308416值/15阶段逐位相同，各只运行一次。这里是普通C++源码模型，未生成RTL。
真实小输入、所有实际阶段输出、冻结源/ELF和日志留本地，Git只收源码和摘要。

[新方案与边界](QWEN2_TRANSPOSED_DENSE_MODEL_20261011_CN.md)记录：前六个K1536
矩阵可驻留A并免C恢复，但down保留全K时需10次A读，令全图DDR为187432960B。
在原互斥iDMA和理想64B/cycle条件下，完整MAC上界50.1415%，不是实测利用率。
下一步只在同一模型比较down的实际DDR-prefix及事务依赖，然后决定生产路由；
不把尚未执行的解析备选或局部PASS代替完整数值/性能验收。

- done（局部）：f28精确CI/源/工件和27份IR核验。
- done（软件局部）：转置映射cold M16/M128完整15阶段保持原v0逐位数值。
- ongoing：down映射选择、真实端口/ACK/返回生命周期和全DAG周期模型。
- ongoing：原M128 native/最终FP32 FAIL及数值政策决定，没有修改门限。
- to do：生产Chisel路由、carried/更长prefill和冻结激励硬件门。
- 保持：Q21.3/U00.2 ongoing，U01 to do，C02.2 OPEN。

## b0e4aa7 终态与同一全图的实际流量减少

`b0e4aa72f9dd6e9f3fef8f70089feeda502096c5` 的 13＋27＋248＝288 项轻量 CI
及 payload guard 完成。234952 B 工件 SHA 为
`de2974bfa478e8051414c79b0d0bb42afdaa15ce2fc606cc2cbc7d265c0ece79`；
前21份报告逐字相同，新转置摘要仅精确 git_head 的预期变化，18个来源pin核对。

[同一候选的新数据流](QWEN2_FULLGRAPH_DATAFLOW_20261011_CN.md)已实际跑过 cold
M16/M128：down 用真实 DDR prefix，FFN gate/up 经实际 SRAM 给 SiLU，禁止从
观测副本取数。15阶段各次663552/5308416值全bit等于原v0；98.95/159.91秒
是软件子进程墙钟，Dense 都执行完整 M128 padding 布局，不能解释为硬件周期。

全图账本由187432960降至131727360B，8个修改owner实际计数与11个原源码公式
复核一致。保持原共享互斥64B/拍条件时，乐观界71.3456%，尚不满足80%目标；
不把局部issue几何99.1220%当整block利用率。下一步落实已选映射的实际Chisel
两组operand路由、bank/owner与prefix/FFN接线，不继续扩张独立模型分支。

- done（局部）：b0精确CI、288测试、22份报告与源pin核验。
- done（软件局部）：同一M16/M128全图真实prefix/FFN存储依赖保持v0位精确。
- ongoing：实际Chisel路由/共享端口/Host接线及完整周期模型。
- ongoing：原native和FP32-final FAIL、数值政策待决定，不改门限。
- to do：carried/更长prefill及冻结激励最终硬件门。
- 保持 Q21.3/U00.2 ongoing、U01 to do、C02.2 OPEN。

## 590f8cf 终态与既有 Matrix service 的真实前端接线

`590f8cfd39a1aa5aa2a2dc481eab29d406d899a2` 的13＋27＋67＋248＝355项模型
CI及payload guard已成功。238313B工件SHA为
`9425e04edd5794f1a50da3021aaa8d94e371c5bee7a4b43a42217a5971e2ea2c`；
23份报告核验，其中仅转置解析摘要的git_head有精确预期变化。新的fullgraph包装
做了合成小门及真实prepare，没有重复实际M128数值运行或生成RTL。

随后[转置service候选](../candidates/qwen2_resident_matrix/transposed_route/README.md)
在原 `MatrixPipelineService` 中接通已选M128×N32的两组weight/activation路由。
模式在group接受时锁存，默认关闭，原4096 FMA、五contexts及队列保持。新增1位
group状态与2304bit源码共享mux及准入比较逻辑，面积与时序尚未测。

真实Scala编译与CHIRRTL展开共两条命令成功；20IR身份、六组默认关闭严格等价，
以及真实组合连接的2,064,384个operand-pair坐标通过。打包后36项模型/身份负测
及两种baseline路径校验通过，原编译和新检查器身份分列，旧PASS未重绑定。
这仍是前端与组合路由门：未执行FPU/RTL时钟协议，现行生产owner和Host尚未启用。

下一闭包是从实际A/B bank按既定物理公式取数并接同一step，绑定单端口、同步
延迟、租约、背压、reset/fault；随后接M128输出和最终写ACK。旧resident seed
读源的A/C/B分区不能未经修改套到已选A688/B80KiB方案；保留这项实际接线缺口。
131727360B与71.3456%仅为软件流量及理想上界，未达到80%全周期目标。

- done（局部）：590精确tree、355测试、23报告/源pin核验。
- done（前端局部）：既有Matrix service的默认关闭转置路由、36小门及真实CHIRRTL检查。
- ongoing：实际bank/owner/Host、down prefix、FFN共享端口与全周期模型。
- ongoing：原M128 native/FP32-final FAIL、数值政策待决定，阈值未改。
- to do：carried/更长prefill与冻结激励最终硬件验收。
- 保持 Q21.3/U00.2 ongoing、U01 to do、C02.2 OPEN。

## fb909e8 终态与实际 bank / owner 源码闭包

`fb909e861ab91dfd7ecc44bc3e86245c3e63b029` 的110项测试、13条Scala/CHIRRTL
命令及payload guard已在CI通过。11,560,736B工件SHA为
`ed6537b4a8588b0d630833f8cc7af8be367cce8e4af5d9f9e5ab9ab4dd45a901`；
47份IR严格对照、3套源码manifest和87依赖SHA核验完成。

后续[默认关闭的owner替换候选](../candidates/qwen2_resident_matrix/transposed_owner/README.md)
已将实际DMA、A/B同步bank、operand FIFO、同一Matrix service、物理结果gather
与末写ACK落实为Chisel源码。只在构造时选旧或新owner，避免双份SRAM；首门准入
M16/M128、K≤1536、N为32倍数，down K8960明确拒绝，Bias仍是原独立Host命令。

48个控制/结构小门通过。真实owner/service编译与12份CHIRRTL通过，严格关闭
模式single/burst两档相同；81份生产/P0/gemmini/HardFloat源码typecheck通过。
完整kernel未展开。每组合均核验32个1R1W bank、688/80KiB、八endpoint/clock
 gate、4096 FMA和既有五context/四operand/八metadata/两result槽。A加载明确有
256bit RMW加256bit上半缓存；没有把端口或存储当免费资源。

真实数值单位门取封存M128 n0和Wq前160通道：实际model bank发出7680个step，
驱动31,457,280次host FMA；同一个model将物理tile经1280写beat、640次ACK写回
81920B。20480个bias前结果与独立raw输入点积全bit一致，ACK结果再单独加bias
也与保存qr子集全bit相同。没有golden返回注入。这是派生N160单位组的主机模型
数值闭包，不是完整投影、Chisel执行或端点FPU验收。56,196协议ticks不代表硬件
cycles；单64B读描述符/逐行写ACK的保守实现也没有给出吞吐提升预测。

首次前端strict比较因三条assert来源字符串失败，证据保留；修正源文件名/行数
后重验，未放宽normalizer。源审查还修复了FP32→BF16 Inf提前拒绝、跨owner
poison准入、模型同拍fault/transfer义务，均未改成功数值或原验收门。
故障终态沿用原唯一在途端口契约，错误tag/LAST只允许错误退休并锁到共享域reset，
不允许成功发布；跨job陈旧响应的fence依赖协调reset，不能用局部generation证明。

- done（局部）：fb909e8精确CI、110测试/47IR与源码/依赖核验。
- done（源码/模型局部）：实际bank/owner组合、48小门、12前端IR/81源typecheck及N160实值闭包。
- ongoing：down真实FP32 seed、FFN保留槽、共享端口/完整Host和全周期模型。
- ongoing：原M128 native/FP32-final FAIL与数值政策决定，门限未改变。
- to do：完整kernel展开与真实端点协议/数值、carried/长prefill及最终冻结刺激硬件门。
- 保持 Q21.3/U00.2 ongoing、U01 to do、C02.2 OPEN。

## 825caff 精确前端 CI 终态与下一依赖

`825caff3a6c618419c49c7da452e009ce86ae8b5` 的158项测试、16条前端命令及
payload guard成功；81个kernel typecheck源码身份、59份实际CHIRRTL与本地
严格规范化对照通过。工件21,345,364B，SHA为
`9520687c90d77459c3102c9cc1d1de6fe1bd00466f6e3fc74d4f0abf3dfa52aa`。
本地早期前端capture与最终CI inventory有4项明确差异：README修订及后来新增
的numeric Python/C++和test_frontend；其余原9项及实际14个编译源码一致。
这些差异单列保留，数值单位门仍绑定自己的capture，不重绑定旧前端PASS。

下一闭包选真实FP32 prefix保存/恢复：先将原N160、K1536实值单位在K768分割，
通过DDR实际写回再恢复同一Matrix的五个accumulator context。真实存储位于
保留SystemVerilog叶模块，Chisel BlackBox新增端口本身不构成接通。需要同时
落实ICG唤醒、完整seed提交后clear=false、错误退休和协调reset。该闭包通过后
再推进已选K2560/2560/2560/1280的down调度；完整down和Host workspace仍open。

- done（前端局部）：825caff精确CI与工件核验；未执行RTL/FPU数值。
- ongoing：真实叶FP32 seed及保存/恢复源码和模型；无新SRAM/array预算。
- 保持原native/FP32-final FAIL、数值政策待定及上述完整block未验范围。

## 默认关闭的真实 accumulator seed 源码增量

[seed候选](../candidates/qwen2_resident_matrix/transposed_seed/README.md) 将内部
prefix workspace、同一owner/service、八个保留endpoint及其既有五bank写口接成
源码路径。新增Chisel端口仅在使能时出现；SV源保留默认关闭参数，没有另外复制
阵列或SRAM。当前证明单位
仍是M128/K1536/N160，在K768保存实际FP32中间量，经全部1280个prefix写ACK和
Matrixdone之后才发布内部generation，再实际读回并恢复五个context。

最终本地模型运行1.50秒；恢复前主机accumulator已清空，1280条seed载荷来自实际
先前写回，不由golden注入。20480最终值与原未分块结果全bit相同，独立raw-input
点积和最后单独bias也全部相同。实际81920B prefix、102400B seed记录和每次运行
源码快照保存在工作产物，不进入Git。协议ticks仍不代表硬件周期或MAC利用率。

75项小门覆盖owner/service、源码绑定和叶协议模型。独立审查发现并修复了忙时
seed begin提前冻结数据而token继续的风险：新issue先阻止，已接受的FMA/result/
flags一致排空，成功reserve后才hold；五个pipeline/结果阶段及背压模型有变异
敏感性回归。这是源/事件模型保证，未执行实际门控时钟或保留SystemVerilog。

84源实际Scala typecheck与7份CHIRRTL展开均退出0。首次检查器把既有Queue误
匹配成smem，原FAIL保留；修成实际cmem之后只审计同一冻结IR，没有重复编译。
12份默认关闭module比较相同，默认/开启端点ABI分别22/45端口。保留SV仅静态
源码审查，未进行SV解析、仿真、综合或形式等价，完整kernel也未展开。

新增寄存器源码/IR记账为owner805、service37、controller138、八leaf872，合计
1852bit；每个既有lane写口增加32bit数据与3bitcontext选择，另有分发/比较逻辑。
仍为4096 FMA、五accumulator context、768KiB SRAM和原4/8/2队列；面积与时序
未测，不能因单元数相同就宣称资源免费或实现了71.35%上界。

- done（局部）：75小门、同输入split实值模型、真实源接线与前端审计。
- ongoing：新提交精确轻量CI；生产Host workspace绑定和硬件reset/seed动态门。
- to do：K2560/2560/2560/1280 down、FFN共享驻留、完整prefill/硬件链。
- 原M128 native/FP32-final FAIL、数值政策待定；其余四个模型block状态未改变。
- 保持Q21.3/U00.2 ongoing、U01 to do、C02.2 OPEN。

## 3206b14 精确前端 CI 终态与 Down 接线

`3206b14227aabbf30f931827e6ece33f899b1bdc` 的 payload guard 和前端 CI 已成功。
233项测试、18条 Scala/CHIRRTL 命令、84源 kernel typecheck、66份本地/CI IR
严格对照及87个锁定依赖 hash 均已核验。工件24,388,394B，SHA为
`ea15eb4cb7382eee830fc2ac4218fda2b2cf82e8ef45984f3f0c2a3fad77aead`。
原825前端与最终inventory的4项差异继续单列；seed源码清单另行区分两份自动
生成的Python缓存，未把缓存视为源码。完整kernel没有展开，未生成RTL或执行FPU。

首次尝试在233项测试通过后，锁定Maven依赖下载返回HTTP404，尚未执行Scala。
原失败日志和1287B工件保留；日志没有给出失败URL，原因未定。随后只读检查87个
原始URL均可访问，仅重试原失败job一次，同一源码和依赖锁成功，不能记成首次通过。

下一增量是实际Down的K8960分块接线：固定768KiB bank中按2560/2560/2560/1280
重载A，每块扫完全部N32 context，真实prefix写ACK和Matrix完成之后才推进下一块。
必须分离全局K/行stride、局部bank K、是否恢复seed与是否最终输出；只扩大K准入
会越过容量或错误发布中间结果。沿用已接通五bank seed，不增加array、SRAM或端口。

- done（精确CI局部）：3206b14前端/源码/工件核验，首次下载失败完整保留。
- ongoing：Down分块源码与真实先前act输出驱动的有界主机数值门。
- to do：生产Host workspace绑定、FFN共享驻留、完整prefill和硬件动态验收。
- 原native/FP32-final FAIL、数值政策待定及其余四个block状态不变。

## 完整 Down M128 的分块源码与模型闭包

[Down候选](../candidates/qwen2_resident_matrix/transposed_down/README.md) 已在同一
owner/service/seed路径落实K8960的四块调度。每块重载实际A后遍历全部N组，全局
K和行stride保持原值，bank只使用局部K。N1536每轮为9组五context加最后3个
context，四轮共40组。K1536等单块操作也可使用同一owner，不制造prefix流量；
N8960单块准入可复用786432B租约，不额外要求未使用的按N扩展prefix容量。

最终21项源/控制测试通过。85个实际Scala源码typecheck与9份CHIRRTL通过，
12份默认关闭module比较保持相同。固定32个1R1W bank、768KiB SRAM、4096 FMA、
五accumulator和4/8/2队列不变；新增宽度/调度/未退休seed状态合计131寄存器bit，
连同先前seed增量共1983bit，另有地址选择与frontier比较逻辑。该账本不是综合
面积、时序或额外资源免费的证明。
前端capture时的主机数值runner/C++仍是N160版本，后来扩成N160/N1536；两项
inventory差异明确保留，实际Scala、模型、patch和pins未变。最终numeric_02和
numeric_full_03绑定新主机源码，前端PASS没有重绑定成主机算术证明。

独立审查发现此前seed-only错误路径没有等待已接受seed的最终ACK。新Down层
已补显式未退休义务：扣住ACK且错误MatrixDone先到时保持drain，没有终态；
ACK真正到达后才允许错误完成并poison。原seed-only候选和首轮Down的前端/数值
capture保持原身份，不能追认为已覆盖此修复。最终源码已重新小批验证。

真实输入来自已执行完整软件图的phase12 act，权重来自固定Qwen2-1.5B L0
payload。最终N160先通过，再运行一次完整M128/K8960/N1536，耗时44.41秒；
430080个bank实际载荷step驱动1761607680次host FMA，196608个最终FP32值在
输出全部ACK后对独立全K点积及原phase13逐bit相同。两次最终运行源码相同；
完整Down的summary SHA为
`5d3688179363fef340cd5a3aab245c41f58f69dd173d25b6747d5c2fdef5794b`。
这是完整Down子算子的主机模型验真，不是完整block、Chisel硬件执行或native门通过。

prefix占用独立DDR区786432B，即48个物理[16][256]FP32 context；不计为新增SRAM。
该区必须64B对齐、合法56bit范围，与A、B、D及未来Host普通tensor/元数据区隔离，
并在launch接受时固定租约。每轮先读取对应旧版本，seed ACK后才可原址覆盖；全部
context写ACK及Matrix完成后才发布下一轮。失败后的混合版本不是可恢复checkpoint，
需协调owner/DMA/service/leaf reset。生产公开Host分配、隔离和实际绑定仍待完成。

完整模型保全了三轮各786432B实际prefix、36864条seed记录及地址唯一索引的
读写版本日志；独立复核全部载荷和最终值，没有重跑算术。该阶段计入A读4587520B、
W读27525120B、prefix读2359296B及总写3145728B，合计37617664B，含prefix
写2359296B和最终输出786432B。未来真实iDMA周期分母必须包含这些读写、元数据、
背压与所有等待；目前计数是模型事件，不是实测带宽、硬件周期或MAC利用率。

- done（局部）：完整Down M128/K8960/N1536实值模型、最终21小门/85源/9IR及capture复核。
- ongoing：本批精确发布/轻量CI；公开Host workspace lease与单一顶层接入。
- to do：FFN共享驻留、完整所选prefill源路径、最终冻结刺激硬件回放。
- 原M128 native/FP32-final FAIL、数值政策待定，Q21.3/U00.2 ongoing、U01 to do、C02.2 OPEN。

`eaed93d8b200d9e3d059a00678a07b2fcb7076b6` 精确CI现已收口：254测试、20条前端
命令、85源typecheck及75份本地/CI CHIRRTL严格一致；87依赖SHA、6源码manifest
与payload guard通过。108项工件文件共28,813,887B，SHA为
`66ba0d4dce34ab9b5cbeb3b86afb0698a35ff7b18445382d84e5512d0124ab7d`。
工件没有执行RTL或主机FMA；全Down实值仍绑定其独立本地capture。前端inventory
的两项host程序修订，以及后来加入的README/manifest，均单列，不重绑定旧PASS。

- done（精确CI局部）：eaed93d发布、远端tree/13blob及上述工件核验。
- ongoing：公开Host workspace lease接线；原完整block与native门状态不变。


### 2026-10-11 公开 Host workspace 接线子门

- 在 `transposed_host` 显式默认关闭 profile 中，将现有第 4 region 接到真实 chunked Down owner，保持 Host launch 833 bit、Command128、typed descriptor 和 `bias_index` 原语义。旧 driver 的空 region3 仍按原模式兼容。该 region 接口来自本仓库 Host adapter，不是上游硬件的保留区承诺。
- enabled 要求独立、64B 对齐、56-bit 范围内的非空 RW lease；所有 4 region 仍互斥，并从普通 tensor、初始 live input 与 metadata 权限中排除 workspace。M16/M128、N32、K≤8960 和多 chunk 容量在 owner issue 前检查。完整 N1536 需外部 786,432 B；single chunk 仍需真实 lease，但免未使用的 N-dependent prefix 容量。
- lease 来自 launch ACK 后的 cfg 快照，epoch 扩宽后 +1 仅作 identity，不构成 checkpoint 或跨 reset freshness。末 owner ACK、completion 和 Host result 背压期间保留；composite poison 同时门控 launch.valid/ready，已接受事务继续沿原路径 drain。公开 Host 无 abort 端口，错误恢复要求 Host/DMA/service/leaf 协调 reset。
- 本地 28 测通过：17 个模型控制门加 11 个 source/frontend 门。模型复用冻结 Down 实际端口控制，包括两命令真实 ACK 写后读、K2688 两 chunk、不同 lease 成功再 launch、epoch0/65535、全部 region3 输入变化、末 ACK、prefix-error seed ACK 排空、错误不发布。Matrix 使用有限 opaque token，不是算术验收；迟到 seed ACK 注入只验证 owner poison→Host admission，尚未验证 inactive kernel 的真实晚 ACK 路由。
- 实际 85 个 Scala 源 typecheck 通过，包括完整 Host top/Qwen owner kernel；6 份实际 Commands CHIRRTL 通过，普通/QKV 默认关闭 IR 与冻结基线完全一致。完整 top 未 elaboration、未生成 RTL、未执行 FPU。plain FP32 A/D 模型已覆盖；V/QKV 仅 source/parser 边界覆盖。
- 小 parser 配置 eventSlots32/maxCommands21 的 enabled/disabled 寄存器相同：Host 131/35,226 bit、record reader 6/334、tensor reader 7/1,278，已有 cfg 833 bit 复用；新增地址算术、比较和门控不能称零面积。保持原 768 KiB/32 bank、4096 MAC、5 accumulator contexts 和同一 iDMA，未扩 SRAM。
- eaed93d 的完整 Down M128/K8960/N1536 实值证据保持原身份；不继承为新 Host 全链数值 PASS。三个 prefix sweep 对同一 lease 的读和写各 2,359,296 B 必须计入真实共享 iDMA 分母；完整图 131,727,360 B、理想搬运上界 71.3456% 仍非完整周期预测/RTL实测。
- done：公开 lease 的 source/model/frontend 接线子门；ongoing：生产 Host/owner/iDMA 完整行为、FFN 同 bank residency、全图模型到 Chisel 对应；todo：完整五 block M128 硬件验收。Q21.3/U00.2 ongoing，U01 todo，C02.2 及原 native/FP32 final FAIL 均不关闭。

- 发布闭环：`f5b9b738aa631d241ec5fe32271fa045c0f9d1a1`，tree `0cf2c618c6dcb148f3b3391c3dd756266c2a95f7`。frontend run `38182040972`/job `114596463759` 与 payload run `38182041004` 均一次 SUCCESS。工件逐项复核 282 tests、22 frontend 命令、7 manifest、87 jar、81 份本地/CI相同 CHIRRTL；artifact `11718466606` 为29,358,902 B，SHA256 `11ad71b00cdf11e6fed88c328aceca96e1dc42a1ade07058d0b2fe0560d44c4e`。保留首次frontend到最终模型/文档/审计器六项来源差异，不把后补文件重绑定为原始编译输入。

### 2026-10-11 FFN 共享 A bank / 16-lane SiLU 子门

- `ffn_tiles` 已在真实 Down bank/owner/kernel 和既有 SiLU owner 增加默认关闭的 typed FP32 端口。固定 32 个 1R1W bank、768 KiB SRAM、4096 MAC 与唯一 16-lane SiLU 不变；新增寄存器 1,981 bit，以及地址除余/比较/仲裁/选择逻辑，尚无综合面积或时序结果。
- A 的低 768 words 保存 M128×K1536 BF16；三个 M128×N160 FP32 slot 各占160 words，高端128 words留空。只有低区 K≤1536 Dense 可与 live tile 共存；冲突 K 明确 Bounds，其他 owner 明确 Unsupported。每次64 B有效 tile读取占512 B SRAM读；写入通过512 B读和512 B写的RMW完成，不能以有效字节替代物理端口带宽。
- control.fire 只表示接受；完整输入标签预检、生产写入退休、读响应消费计数和最终release后观察共同约束发布。独立审查修复了非法末release提前成功、abort与finish同拍漏报；模型覆盖背压、已接受RMW排空、held response、非有限值、错误结果和协调reset。
- 最终87个实际Scala/HardFloat源码typecheck与10份CHIRRTL通过，默认关闭三个模块IR与原版等价。完整Host/kernel只typecheck，没有完整顶层展开、RTL生成或硬件算术执行。首轮仅assert诊断位置差异的失败及后续修复快照保留。
- 既有v0软件producer的gate/up实际经bank模型读出、按原C++ recipe计算、写入act并完整读取后比较，35,328个FP32值对独立平面计算和原act均0位差；保留区、空闲区和所有未写lane哨兵不变。M16来自M128首16行，N96是人为末列窗口，均不冒称独立完整block。host时间、模型tick、SRAM字节不是硬件周期或MAC实测。
- done（局部）：共享bank typed端口、同一SFU借用、源码/控制/实值子门及独立review；ongoing：本批发布和精确CI、Matrix真实结果直接tile写回、Host三命令完整预检/融合与下游act消费；todo：完整prefill硬件回放及五block M128验收。
- 原完整图131,727,360 B/71.3456%理想上界尚未由该硬件实现兑现。原native/FP32-final FAIL和数值政策待定保持，Q21.3/U00.2 ongoing、U01 todo、C02.2 OPEN。

- 本批已发布 `17baa23c1d540681c52038ea8a224dc7fd96e811`，tree `e6a8022713f67e1ce77fa9faddeee7869f366e4b`。frontend run `38184311009`/job `114603266021` 与 payload run `38184311016` 均首次成功；工件核验328 tests、24条前端命令、8 manifest、87 jar及91份本地/CI严格一致IR。artifact `11719176753` 为33,772,252 B，SHA256 `abd1ee1174d2e7dfbba0bd04950f3648582239810131167c57c8de8766197ead`；复核摘要SHA `481924e46a217ac5f50a467ce58cbbcb45c699e583585e01a1e88b828d5867b3`。实际三窗数值仍绑定独立local capture；最终runner仅来源校验封装变化明确单列，不把CI当实际producer重跑。


### 2026-10-11 Matrix 实际返回 → FFN 驻留窗口子门

- `ffn_window` 在独立、默认关闭的源码 profile 中接通真实 Dense owner/kernel 的内部 window 入口、实际 Matrix 返回写入既有 A bank，以及带完整 base/dtype/M/K/byte-stride/identity 的 A lease。`job.n=8960` 保留全行 stride，窗口宽度只控制执行列范围；Gate/Up 的完成是 tile commit，真实 DDR writeBytes 始终为0，不送旧 Host done，不发布虚假 DDR live 范围。
- Matrix 结果用原16 KiB finalValue与8-bit游标重排，tile增加只在begin锁存的context-major写序。写RMW仅等待已接受同步bank响应，不能等待整个operand FIFO清空，否则会与两槽Matrix结果队列循环阻塞。末RMW/seal、所有Matrix结果、已接受内存与错误drain退休后才完成；raw abort、aFence同拍失效、held完成及普通命令准入均纳入审查/模型负测。
- 最终28个端口/控制模型门、14个数值/身份小门、8个源码门与1个交付门通过。89个真实Scala/HardFloat源typecheck、14份CHIRRTL通过；完整Host/kernel仅typecheck。默认全关闭与旧tiles-on/window-off的端口及规范化IR都保持相同。相比17baa仅净增262个metadata寄存器bit（owner259、bank标签3），固定32个1R1W bank/768 KiB、4096 MAC、单一16-lane SiLU及原result buffer不变，组合逻辑面积/时序未测。
- 实值路径从既有v0完整软件图phase9 n1与固定官方权重开始：实际DDR地址载荷→A/B bank→接受的Matrix packet→逐K FP32 FMA→Gate/Up tile RMW→实际bank读出的SiLU输入→act写后回读。golden只在真实输出完成后比较，未作为中间初始化。M16/K1536/N32/ng0与M128/K1536/N160/ng160分别0.987/3.518秒host时间；每个Gate/Up/act分别512和20,480个值，对独立raw计算与保存producer均逐bit相同。
- M128 Gate首次A读786,432 B，Up的A读取和ingress RMW均为0，整个链的低区A hash相同。每个投影7,680实际packet、5结果、1,280 tile拍；权重各读491,520 B，ng160的B首offset320、末27,507,776，完整8960 stride确证。DDR、有效tile字节与物理SRAM流量分别记录；这些是模型事件，不是实际iDMA或硬件周期/MAC实测。当前只验一个N160窗口，56窗完整FFN尚未验收。
- 两份成功capture保持模型4219c2f身份。随后最终1c9f69be仅修普通job未接受时冲突预检，以及新接受的拒绝任务计数清理；独立review确认window路径无变化，28模型门覆盖修复，但不将原capture改称新源码执行。数值runner/C++未改，precision pins为未来复现更新。首轮M16的trace UInt32/tag错误发生在首个A descriptor、算术前，修复为UInt64后的新capture及原失败均保留。前端最终auditor只新增净寄存器账与只读重验，编译源/IR hash保持，未重编。
- done（局部）：内部window真实源码、A lease/typed completion、实际Gate→Up→SiLU模型与独立review。ongoing：精确发布/轻CI、公开Host三命令预检/融合及act沿原DDR ACK路径排出。todo：56窗完整FFN、原Down真实依赖、完整prefill冻结刺激硬件回放。原native/FP32-final FAIL、待定数值政策与Q21.3/U00.2 ongoing、U01 todo、C02.2 OPEN均保持。

- 精确发布闭环：`c761ec824ce2c027a66c22feb4a2154829f9d545`，tree `782d2f6137103a2df99a14d0f586bf8ae57ca7c8`。frontend run `38186195126`/job `114608913627`、payload run `38186195183` 均首次SUCCESS。工件150项/39,332,729 B，SHA256 `2be5222d1eee6c82391ad1c2080ec78825fe88c9d058715633551688acedf520`；独立核验379 tests、26条前端命令、9 manifest、87依赖与105份本地/CI严格一致IR，真实资源账净增262 bit。复核摘要SHA `f3a074eb56ee87fbe63c6809d3e9edd3bfaf93a025980cda2478683b4f1e6be0`。前端auditor更新与实值capture的后续ordinary模型修正继续单列，CI不冒充actual模型/RTL重跑。

### 2026-10-12 FFN act DDR 排出与生产 Host 三命令协调子门

- 新 `ffn_drain` 默认关闭端口从 slot2 的真实 FP32 act 读取，复用原16 KiB finalValue、游标和 Memory/BurstMemory ACK 路径，以全64B mask写到 `dst + (row*8960+ng+column)*4`。每次 burst 限制在1KiB内，逐个真实成功ACK累加 DDR writeBytes；全部 tile读响应、写ACK、release退休后才完成。tile commit 与 DDR commit 的语义保持分开，没有用形状推算成功字节。
- 非法span/alias/lease/dtype/窗口在DMA前拒绝。正常成功保留 A lease供下一ng复用；abort、错误和reset使租约失效，已接受事务仍排空。独立审查发现并修正外部SiLU合法idle响应误报，以及未请求响应同拍仍可能接受新读写/消费held成功的缺口；末ACK、同拍poison、release观察和协调reset均有定向门。旧0020前端结果保留原来源，最终0024重新验证，未替换旧证据。
- 最终 drain 63测试通过，91个实际Scala/HardFloat源码typecheck与20份CHIRRTL通过；默认关闭及window-on/drain-off IR保持相同。新增74个metadata寄存器bit，复用原buffer，无新增SRAM/Matrix/SFU/iDMA。完整top只typecheck，未展开或生成RTL。
- 两个真实模型capture从冻结n1和官方权重开始，经实际Matrix packet逐K FP32 FMA、Gate/Up tile、借用既有16-lane SiLU recipe、owner仲裁的tile端口，最终写入以真实DDR地址唯一索引的哨兵内存。M16/N32/ng0与M128/N160/ng160分别1.064和4.151秒host时间；Gate/Up/act分别512和20,480值，对独立raw计算与原v0 producer全bit相同。M128的81,920B输出对应1,280完整写拍、256个独立tag ACK和每行[6,4]两个burst，最终ACK前slot2仍有效；4,505,728B未写区域和canary保持。独立只读复核重建全部DDR/ACK轨迹，无算术重跑。真实iDMA、全56窗口、Host执行和RTL均不属于该数值结果。
- 新 `ffn_group` 在显式默认关闭的Qwen2 resident profile内挂到真实 Host/kernel：复用公开Dense20、Dense20、Activation35和原descriptor reader，按shape、完整allocation、权限、events及workspace匹配，不绑定固定PC/私有地址。先预检三命令，再扫描整个program的primary roots，禁止任何别的命令读写虚拟Gate/Up span；此前A producer和后续普通A复用仍可合法。没有新增Command128变体或复用bias_index。
- 实际协调器按56个ng顺序执行Gate→Up复用A→SiLU→act DDR drain；每阶段使用真实typed owner终态与原flush/ACK，全部act字节完成后才退休A lease并依次交付原三个PC completion。group错误/abort/held回复poison不能提前发布虚拟Gate/Up或act。模型覆盖M16/M128全部56窗调度、全program roots、counter/背压/error/reset，但owner结果是opaque token，不能作为56窗算术证明。
- group最终52测试通过，包括43控制模型、8源码门和交付门；95个真实源typecheck、6个有界IR通过，普通Host/旧bridge的disabled IR相同。完整Host/kernel只typecheck；parser、coordinator及bridge为有界展开。新增账本6,381寄存器bit：coordinator3,389、Host2,398、生产中新实例化的迁移bridge592（含512-bit hold），以及source-only kernel/top poison各1；旧tiles账本已包含外部bridge592，累计时必须只算一次。无新增SRAM/算术/DMA，组合逻辑/面积/时序尚未测。前端编译后只改auditor资源账与README，旧source/IR在只读replay中保持相同，不把后来工具改动冒充原编译输入。
- done（局部）：真实act排出源码/有界实值、生产Host三命令协调源码/控制模型和独立审查。ongoing：本批精确发布/轻CI、整个56窗真实模型与Down直接依赖。todo：完整Host/iDMA行为、所选完整prefill及最终冻结刺激硬件回放。原131,727,360B/71.3456%仅整图理想搬运上界，尚非硬件兑现；原native/FP32-final FAIL、数值政策待定、Q21.3/U00.2 ongoing、U01 todo、C02.2 OPEN保持。

### 2026-10-12 6510a1d 浅克隆基础设施失败与修复

- 已发布源码 commit `6510a1d4f4dd6b6bb7ca6ceb3df72655e3d8ab67`，tree `fb42f812a41061b3c562aee7e75ed3f97bbc4590`，28文件/503,806B；远端tree、每个blob和本地字节已核对，其他20个工作树修改保留。
- payload run `38189186423` 成功。frontend run `38189186428`/job `114618058880` 为真实FAIL：494小测试与前9层26条前端命令先通过，新增drain在读取固定父提交c761的route manifest时因浅克隆缺对象退出128。新drain/group在该CI中尚未编译，不能用本地前端PASS替代CI终态。
- 原日志和artifact `11721061645` 保全，151项/39,338,858B，SHA256 `6ae8d5a89d74ace039b48e12bdca096a0becfe0e608777c371f728ac6aae4976`。失败没有数值执行、RTL或超预算，不改为算术FAIL，也不抹掉基础设施FAIL。
- 修复只给原workflow显式增加固定c761的depth1 fetch及cat-file probe。用新的局部浅克隆复现缺父对象，再验证5个固定baseline的完整tree与全部blob均可获取；c761 manifest逐字节匹配。另补2个轻量门，从实际脚本BASE/COMMIT及manifest收集引用，逐项检查fetch/probe闭合，覆盖每个baseline的遗漏、改成main及错误probe。现有测试文件9/9通过，未运行Scala/RTL。
- 本次不改任何owner、模型算术、source pins、数值门限、工作负载或15分钟预算；后继修复提交需重新完成原两门与工件核验。完整56窗实值和所选完整block/native门仍待完成。

- 浅克隆修复闭环：`ecc8aafd6f9a493fe260023c546a6b7741a18ea2`，tree `17c154c51d42fc4f43af63a39115dd5492924950`。原两门 frontend `38190071758`/job `114620718573` 与 payload `38190071834` 均首次SUCCESS。496测试、30前端命令、11份来源manifest、87锁定jar及131份本地/CI规范化IR全部复核；新增drain91源/20IR和group95源/6IR这次确实执行并通过。artifact `11721517979` 为184项/48,428,595B，SHA256 `7ec7d82ea0f52380076463d936926921481ed88b3c4c5247b9921453d06d91bf`，复核摘要SHA `60cafb43d0ef2b434205380ba2310e72d94bf5c07a9d65ac031c7640a8599b4c`。逐项确认repair仅CI/test/doc，实际owner/model/算术与6510源码相同；旧FAIL不覆盖，新来源差异和资源账仍分别保留。完整56窗实值与Down直接消费进入下一模型门，当前没有新增RTL/native通过结论。


### 2026-10-12 完整56窗 FFN → 同 owner Down 实值模型

- 从冻结v0 n1和三份官方BF16权重开始，公开组的Python协调模型逐边沿驱动同一owner/bank：56个Gate/Up驻留窗口、真实tile读出的原SiLU、act地址唯一索引DDR写ACK，再由同一owner完整Down读取这些实际act数据。中间未注入保存producer/golden；保存phase10–13及独立计算只在Down末ACK/终态之后比较。
- M16和M128分别199.869/279.681秒host wall，全Gate/Up/act/Down对两条比较源均0位差。M16是冻结M128前16行，非官方独立16-token forward；M128完整覆盖128行。M128共3,637,248个FP32比较元素，112个真实投影typed终态、56个act drain及4,587,520B实际ACK，Down最终786,432B ACK后下一model tick才终态。原始输入、76个源码快照及输出hash独立只读复核通过。
- 一次A载入贯穿56窗；Gate/Up虚拟DDR哨兵始终不变。三轮prefix各786,432B只有实际ACK后才回读/seed，seed ACK后才覆写，所有物理4096 cells/context和padding均检查。单元门覆盖coordinator-only错误时仍有读在飞、held SRAM响应丢弃、最后ACK背压、完整mask/1KiB、alias、复位和多K chunk；SiLU主机调用是同步recipe，尚不是硬件SFU延迟模型。
- M128 payload流量98,041,856B：A786,432，权重82,575,360，act写/读各4,587,520，prefix写/读各2,359,296，Down写786,432；不含完整block/metadata。主机观察有效/物理FMA均5,284,823,040；M16采用相同128-row物理映射，有效660,602,880、物理同M128。因此约200秒M16并非线性M缩放，且这些不是Chisel/RTL计数或硬件利用率。固定4096 MAC×完整硬件wall分母仍无实测值。
- 本增量只新增模型编排、测试、pins/紧凑摘要和CI小门；旧owner/Chisel/C++算术源保持相同。两份成功capture保持ecc8aaf执行身份，全文轨迹只留明确有界前缀与全流hash；原始输出/prefix/权重仅本地，不上传Git。前序ecc8aaf的131IR前端闭环不冒充本次数值硬件执行。
- done（局部）：完整FFN子图M16/M128真实软件端口数据依赖、独立review与实际capture；ongoing：本批发布/精确轻CI、生产Host/parser/shared-iDMA行为对应及完整所选图；todo：完整五block M128和冻结刺激硬件回放。原native/FP32-final FAIL与政策待定不变，Q21.3/U00.2 ongoing，U01 todo，C02.2 OPEN。原整图131,727,360B/71.3456%仍是理想搬运上界，不能从FFN子图推成硬件兑现。

- 发布与工件闭环：`812d858f8e33e1e6da0cac354846465e971aa975`，tree `29501548b0c499f914bfff2ead19cba43afb2084`。frontend run `38192104398`/job `114626872092` 和 payload run `38192104433` 均首次SUCCESS；日志实核14个suite/514 tests、30条前端命令、11来源manifest、87锁定依赖及131份本地/CI严格相同IR。artifact `11722430435` 为48,428,613B，SHA256 `901bf26d161cecea62336df69491e0747c1521e8a720698a809bf08d8b68e888`，复核摘要SHA `96905f7b370dea3ea49a7700b65eca6d781dd1c0a49928f3f899178bbc49f411`。CI包含小合成数值门，未重跑官方载荷M16/M128；两份实值capture保持原独立身份，未新增RTL/native通过。下步消费公开Command128/descriptor实际字节，接到同一Host/group/owner链。

### 2026-10-12 公开字节到 FFN4 的模型接入与普通 Down 发布栅栏

- 新 `ffn_public` 复用原公开 packer 生成4条Command128和43条descriptor，按64B真实地址读取，保留尾维填1、元素stride、权限、offset、policy与全program primary-root扫描。没有私有opcode、地址槽或bias_index约定；命令/descriptor、8个tensor和workspace共11个完整物理span互斥。
- 同一Host模型真实发出一个驻留组请求和一个普通Down请求；同一owner/bank依次执行56窗Gate/Up、原SiLU、act写ACK，再读取实际act进入完整Down。原三个组completion与第四个Down completion均通过正常公开路径，算术golden不参与命令发出或中间初始化。
- 真实源码审查发现：原三处raw-poison发布栅栏只覆盖resident pending，普通Down held success可能漏过。修正只在enableResidentFfn profile内覆盖普通成功，Top直接加入既有owner总resetRequired；done.ready/在飞ACK排空不变，普通明确error保留。completion.fire之前成功可被隔离阻断，fire之后已发布event/span与held最终result不能被迟到poison追溯撤销；全局quarantine没有epoch字段，不构造跨reset freshness。
- 修正版52个控制门（新增9门）、8源码组合门和12个真实小算术/ACK门通过，包含同拍terminal/ready/poison、末ACK背压、重复ACK、错tag、fire前后两种边界、错误排空与协调reset。95实际Scala源typecheck、6有界CHIRRTL通过；两份default-off IR相同，寄存器增量账仍6381bit，无新增SRAM/Matrix/SFU/iDMA。完整顶层未展开，组合门控面积/时序及网表环路未验。
- 公开adapter另31门通过，capture封装10门通过。首次prepare-only误把仓库内venv的numpy/yaml工具计入源码闭包，在读取数值/编译之前失败；保留原回执，修为仅将当前sys.prefix的site/dist-packages归为工具并记录版本，其他repo/work实际依赖仍fail-closed。新的严格执行闭包48源、26项实际Python imports，另47份历史inventory只作保存，不冒充执行源；旧812d858 capture/pins保持原身份。
- M16新公开FFN4捕获已成功：304.597秒host wall，四阶段对独立固定算术和原v0 producer前16行均0位差；act573440B经1344 ACK完成，Down98304B，公开最终4completion/2job/671744B。Down末ACK model tick3142521、owner终态3142522、公开completion3142527，全部在参考比较前。metadata87个64B读取共5568B，逐record地址/slot/word已独立复核。M16仍是冻结M128前16行，不是独立官方16-token forward；这些tick不是硬件周期。
- M128同48源单次执行已EXIT0：437.927秒host wall，四阶段3,637,248个FP32元素对独立算术及保存producer均0位差，act4,587,520B和Down786,432B全ACK；末ACK model tick4,674,597、owner终态4,674,598，公开4completion/2job成功。metadata仍87×64B，FFN payload98,041,856B加metadata为98,047,424B。观察有效/物理主机FMA均5,284,823,040；不是Chisel/RTL计数，whole-wall硬件利用率仍null。本路径仍只FFN4子程序，输入为原v0 n1，前置Attention/Norm/residual不在该数值闭包。原完整block native/FP32-final FAIL、政策待定、Q21.3/U00.2 ongoing、U01 todo、C02.2 OPEN保持。
- CI入口只增加新公开子门和其不可变812d858 baseline fetch/probe；浅克隆依赖集合由5扩到6并保留逐项缺失/漂移负例。测试prepare显式使用当前测试checkout HEAD，生产默认源baseline不变。仍只触发frontend/payload两门，未扩大15分钟预算或触发完整RTL批次。

- 两个新actual capture已独立只读复核：48源运行前/后及冻结副本、4实际输出对保存producer逐字节、3prefix文件与87条metadata原字均一致。M128公开Down completion tick4,674,603晚于真实owner终态；紧凑摘要35,953B独立绑定原完整summary，数据不入Git。done（局部）：公开FFN4 M16/M128源/控制/数值闭包；ongoing：24文件小批精确发布与两门CI、完整所选prefill图；todo：完整五block验收与最终冻结刺激硬件回放。

- 发布前独立摘要审查纠正一处统计：112个窗口回执里的A-load fence是累计值且每项恒为1，不能求和为112。紧凑字段改取最后累计1，并加交付断言；旧草稿摘要与tree清单保留，实际capture/算术/控制源码未变，未重跑数值。

### 2026-10-12 4982f09 公开 packer 的 CI 依赖修复

- 24文件源码已发布为 `4982f09253d34e8803fbe1984c2190c9fc0edfe1`，tree `62408eb1d20c0c94df444a233fc0171c24b144dc`，远端逐blob与本地索引复核一致。payload run `38196767890` SUCCESS；frontend run `38196767794`/job `114641051742` 在单测导入阶段失败，前12组506测试通过，公开suite出现3个import/setup错误。Chisel编译没有执行；工件步骤因尚未产生frontend文件而失败，没有该轮IR产物。
- 原始日志确认为 Python3.12 无 NumPy：公开 `heteronpu.command` 导入包初始化后进入 `cgra_sfu.py`；同一初始化还导入 `config.py` 的 PyYAML。二者都已是 pyproject 声明依赖。修复只在该工作流的测试前从 PyPI 安装固定 `numpy==2.3.5`、`PyYAML==6.0.3`，与实值capture工具版本相同，并以实际Command128/DescriptorRecord导入作smoke，不跳过包初始化。
- 干净Python3.12 venv先复现缺NumPy，安装两依赖后，6个不可变baseline对象probe、公开包导入以及完整15组580个轻量测试均通过，其中公开suite55门。新增依赖守卫从pyproject核对完整依赖集合，拒绝漏包、浮动版本、额外包、未审核registry和导入顺序错误；与既有浅克隆baseline负例合并作为发布前预检。单次本地预检runner在580测试结束后因过宽命令筛选误选一个frontend入口，在读取本地jar前失败，未启动Java/编译；原记录保留，筛选已限定test路径，没有用该调用声称frontend通过。
- 本补丁只改变workflow、其测试和中文记录。48个实际执行源、两份M16/M128数值capture、固定算术、所有阈值和95源本地前端证据不变；不重跑M128。ongoing：修复提交的精确远端/两门CI与工件核验，成功前不把4982f09的失败改记通过。完整block/native政策与五block状态保持OPEN。

- 依赖修复已在 `8212a32f43338163baee4126e522dcacede0fa23` 闭环，tree `ef217131a12287ec737e5b424bdd94e45e755dc2`。frontend run `38197612950`/job `114643703757`、payload run `38197612963` 均首次 SUCCESS。工件 `11724337644` 共48,428,595 B，SHA256 `b1b9c24bab6d135667fd6718dc5731518980056b4aa0fe9d399350fc9f33779c`；独立核验580 tests、30条前端命令、11个源码manifest、87依赖和131份本地/CI一致IR，184个归档项。核验摘要SHA `80f77b48477c04c072773400a670a42da1d08ee43831a15cf1c8f907ffbb919c`。4982旧失败与未编译事实保留，未将它重写成成功。

### 2026-10-12 公开21命令 raw x→KV 的实际 M128 前缀模型

- 复用原21命令/215描述符 packer，只通过原BF16转换器改变Dense权重dtype；35个真实分配互斥，两个cache view解析到同一KV分配。`legacy_prefix` 默认关闭，解码现有Norm/Bias/RoPE/KV合同。新唯一物理地址内存同时服务实际metadata读取端口、三个Dense与前缀owner；普通Dense沿用同一Matrix/A/B bank及原accepted-step FP32 FMA，没有测试私有输出槽。
- 从固定Qwen2-1.5B L0原raw x、gamma/bias、QKV BF16权重开始，实际顺序完成pc0 Norm、Q/Bias/RoPE、K/Bias/RoPE、V/Bias、pc9 KV。全部中间写回经真实模型command/data/ACK、owner终态与public completion后才可读取；末ACK背压、每次旧输出共存hash、全canary、未执行suffix与virtual哨兵均检查。QKV K1536不使用外部prefix workspace，完整Down后续必须将其真实workspace写后读接到这个统一地址模型。
- 同源M16先过后才执行M128，分别22.985/48.492秒host wall；126,976/1,015,808个FP32值均与独立原C++方法逐bit相同，包括bias前qraw/kraw/vraw。保存producer只比较n0/qr/kr/v/q/k六项及其k/v组成的KV，未错误比较Attention。写ACK分别507,904/4,063,232B，两case各10个public completion，无整个block terminal。M128读14,425,088B含7,168B metadata，读写合计18,488,320B。这是软件端口流量与主机时间，不是真实DDR或硬件时延。
- M16摘要SHA `d62c999b3d08ce224c3d56d76059a38ed76e8480b8824b651c04febf6f1dd803`；M128摘要SHA `edd4f19e29945e89d7280c949914fb2370969216cdcb856f20eaca9e5b234502`。63项源码live/frozen/执行前后完全一致，31个Python导入纳入闭包。独立只读复核重建9个readonly分配的来源、10个实际输出及参考、metadata、ACK、哨兵，不重跑数值。原FFN4的48源旧PASS保持在不可变8212提交下，不能为新前缀源码继承。
- 新模型门包含Norm真实公开链、读写guard与实际metadata端口身份、abort排空、原scalar/Vector异常语义、M16先验完整性和纯源码CI依赖。独立review修正了检查错误metadata引用、M16空比较集合可真和编译argv插入未记录TU的漏洞；首次本地guard还依赖work缓存，已改成完整synthetic临时fixture并验证禁止work产物读取。原失败/修正记录保留，未改算术/阈值或重跑旧M128。
- 观察M128有用/物理主机FMA均402,653,184，M16为50,331,648/402,653,184；硬件whole-wall周期/利用率保持null，不能用模型ticks计算。无RTL/EDA、无新增硬件资源证明；Norm软件row数组不冒充物理bank分配。done（局部）：公开pc0–9 cold M16/M128实值闭包。ongoing：精确小批发布/轻CI、同一launch余下Attention/O/residual/postNorm/FFN/Down/final residual。todo：真实统一workspace、完整五block M128及最终冻结刺激硬件回放。原native/FP32-final FAIL、数值政策待定、Q21.3/U00.2 ongoing、U01 todo、C02.2 OPEN不变。

### 2026-10-12 公开21命令同实例整图软件数据链

- 前缀提交 `df18ba25a439fd90c846b22b9aafe992a2a6ae79` 的两门已闭环：frontend run `38202658177`、payload run `38202658181` 均首次SUCCESS。工件 `11725324275` 的48,428,601 B与SHA `d108993e0e8a7a87695055e8960437b18c5471739ab3416879219d6a4748c83b`已核实，653 tests、30条frontend命令、11份manifest、87依赖及131份与本地相同IR全部核验。原pc0–9旧PASS保留在df18源码，未重新绑定后继实现。
- 本次接通原21条Command128/215描述符，从原始x顺序经过输入Norm、Q/K/V及bias/RoPE、KV、QK/softmax/PV、O/residual/postNorm、56个FFN驻留窗口、完整Down及最后residual。单launch复用同一物理地址模型、Dense owner/五bank、唯一81920 B软件Matrix accumulator，以及原共享Scalar；所有中间输入均从先前实际写回或已接受的驻留结果取得。预启动不填任何中间结果，完整terminal以前禁止加载golden比较。
- normal QK/PV与转置Dense通过同一Matrix服务的实际result/done/seed-ACK及owner退休边沿交接。QK保持原8拍分片及16项归约，PV保持逐key row0，未以新的GEMM次序替代。独立review发现原endpoint不传播算术flags，因此模型先前过强的“任意非选中单元溢出就拒绝”已修为原核心只检查选中结果finite；新增非选中Inf合法、选中Inf/NaN拒绝回归。Scalar和原浮点舍入合同未变。
- 两个residual Add遵循原ElementwiseMemoryEngine的完整1024元素tile双输入加载、全部计算后再写回与原fatal flags策略；有效域是本次hidden1536/KV256和16lane整除，不扩称任意tail。公开workspace只走已授权第四region专用生命周期，普通tensor访问拒绝；Down真实三次786432 B prefix全ACK、同版本读回与seed ACK后才覆盖。Matrix窗口错误退出保持poison与在飞资源，不能由Python finally清引用提前解锁。
- 干净Python3.12首轮整组public测试发现共享解释器中另一测试导入l9，触发旧capture严格import闭包。保留失败日志，严格闭包未删；改成完整发现每个test文件，各独立解释器运行并汇总源SHA、测试数、退出码和日志SHA，任一失败、空测试或跳过均总失败。原14个文件158 tests和其余小门全部通过；新harness6门覆盖失败继续收集/隔离/timeout等。该harness身份独立于正在执行的75源数值快照。
- 验收范围仍是Python/C++源对应软件模型。没有执行Chisel/RTL，没有真实iDMA或硬件cycle实测；host FMA与协议tick不会填入whole-wall硬件利用率。原native-v0、FP32-final FAIL及未批准政策不变。Q21.3/U00.2 ongoing、U01 todo、C02.2 OPEN；五个典型block的完整M128硬件验收尚未关闭。

- M16完整模型原单次PASS：391.085秒host wall、15阶段663,552值及额外rawQKV/KV共704,512值逐bit一致。M128在05:30:55 UTC真实到达21 completion/17 jobs/唯一whole terminal，随后参考只剩29.024秒，在1200.035秒原预算回执记FAILED；不能将它重写为一次正常通过。
- 独立后处理复核冻结前已有的原C++参考：相同source/ELF/编译参数、完整128行输入/positions/arena和15阶段hash，再比较实际15阶段5,308,416值、额外rawQKV/KV327,680值，合计19输出5,636,096值全部逐bit相同。未重跑模型或参考。原失败摘要SHA `9c03b96cfd581447e7d64f7f053cb5410a0299380f8bc6ecb4155aece20ee111`保持；75源在后处理再次核对。17个输出反查原终态摘要的hash/bytes/ACK/published，Gate/Up原驻留observer文件没有原bulk hash，明确以该原运行文件为来源并在后处理首次记录hash。此限制没有省略。
- M128实际Host终态有效MAC6,014,828,544，等于七次Dense有效5,989,466,112加QK/PV有效25,362,432；实际C++FMA6,801,063,936，等于Dense的1,462,272×4096加normal的1,585,152×512。两个mode互斥共享同一accumulator、118次owner acquire/response/release全部闭合，未把两个mode相加当新增阵列。固定资源4096 MAC/拍，最乐观issue周期下界3,047,424，利用率上界为6,014,828,544/(4096×3,047,424)=48.18705897%。没有将模型tick转换成硬件周期。
- 完整实际软件物理流量为读217,227,904 B加全ACK写15,728,640 B，共232,956,544 B，包含metadata、全部tensor和workspace；ACK字节表示写入数据，不再把ACK响应当一次payload相加。Host DDR writeBytes13,369,344 B之外还有3×786,432 B staging prefix写回，二者差额恰为2,359,296 B。若采用共享读加写64 B/拍的明确分析假设，至少3,639,946拍，对应40.34301608%乐观上界。实际iDMA/DDR是否满足该共享预算尚未测量，不能当普遍物理上限或完整周期预测。
- 原理想整图131,727,360 B/71.35%与当前旧Attention映射232,956,544 B/上述上界是不同映射，保留版本和公式。下一最小整改候选先检查KV跨query复用和normal Matrix的有效lane映射；cold M128的FP32 K/V共有262,144 B，要先核真实bank可用容量/单读写端口/生命周期，不能凭空增加SRAM。原QK为16个分片分别FMA再顺序归约，改成普通连续K GEMM会改变v0舍入，必须先以同源数值模型证明或等待明确数值策略决定。当前只收本批完整模型证据，不据此启动无门禁利用率优化。
- done（局部）：公开原21命令的cold M16/M128源对应完整软件数据链与固定算术逐bit验证，原M128超时及独立后处理身份同时保留。ongoing：本批源码/精确远端/两轻CI、实际Chisel整图路由与既有官方数值差异；todo：carried/更长prefill、五典型block的完整硬件回放与真实whole-cycle MAC验收。原native-v0、FP32-final FAIL及未批准政策不变。


### 2026-10-12 cefc79e 冷源码夹具修复

- 完整模型源提交 `cefc79e2a127b3a60203c2600ead11c21793eccc` 的 payload run `38209623653` 成功；frontend run `38209623739` / job `114680656406` 在单测阶段失败，未执行Chisel前端。严格隔离runner拒绝了3个skip：测试误依赖本地历史FFN work下的库/摘要，CI仅执行public165项。原失败工件12,240 B、SHA `13585f341c511bdcdaa13dba4586fd7c303fcecf07b0cd0c8698df566271b69e`、日志及失败结论保留。
- 修复将三项driver测试接到workflow本轮现编的共享Matrix/原SiLU库；显式要求库与编译receipt，核绝对checkout/输出路径、3份源码编译前后hash、完整编译argv、compiler和库hash/大小。缺件、漂移、额外TU或非strict flags均失败，没有历史缓存fallback或SkipTest。原测试曾使用带-frounding-math的旧单独Down库；现在使用当前已验共享库的原-O2/-fno-fast-math/-ffp-contract=off构建，未声称两个ELF相同，未改变算术源。
- 发布前在全新源checkout和全新Python3.12 venv中冷启动，未复制历史work目录。先显式获取7个固定Git baseline并probe，再安装固定NumPy2.3.5/PyYAML6.0.3，现编唯一共享库。完整18组776 tests全部通过，包括public16文件168项、原skip的driver3项和新增6个编译来源负例。冷门摘要SHA `3dcaece39c1412a5603592e544459212d45e0dd85200f07af8fbe06f90b78a52`，现编库SHA `22da518dc47e641cd7052b84d0c46389fd92d71665276fb671410cf5b994136c`；所有75项实值执行源在原工作区和冷checkout均与捕获快照相同。
- 本地第一次冷预检发现浅源克隆未带不可达baseline对象，补齐上述精确fetch后才运行测试；之后本地汇总器以basename匹配完整相对路径误判已成功public结果，保留原记录并修正汇总后继续剩余组，没有重跑已完成测试。全部原日志、每组计数/退出码及explicit构建产物保留。此为夹具可复现性修复，没有重跑长M128、Chisel/RTL或改变数值政策。
- done（局部）：冷源码完整轻门与来源绑定。ongoing：修复提交远端和两CI终态/工件核验；原cefc失败不重写。完整M128软件固定算术证据、原1200秒失败和独立后处理PASS同时保留；native-v0/FP32-final FAIL、数值政策待定及五block硬件验收OPEN不变。


### 2026-10-12 ce7bda 跨阶段输出目录修复与完整冷流程

- `ce7bda275033f0bfc6a062a6b9755920e662dcd2` 的 frontend run `38211082143` / job `114685163115` 已在CI真实通过776项测试，随后因测试提前创建 `work/matrix-interface-frontend` 而触发原“输出目录必须全新”守卫；Java编译尚未启动。payload run `38211082246` 成功。失败工件16,552 B、SHA `141fbe879a648b614cbefba1f850c3bc96828bd93206dc3d5f900c72027b6dcb`及原日志保留；这是跨阶段目录生命周期缺口，前轮只跑单测的冷验证没有覆盖它。
- 最小修复把共享库和public测试产物放到兄弟目录 `work/matrix-interface-tests`，Chisel原输出目录及fresh拒绝保持，入口另显式检查不存在。工件收集同时覆盖两目录。新增2个定向测试拒绝当前已知Python --out命令碰撞、丢fresh guard或漏工件模式；不声称这是通用shell输出分析器。
- 发布前在第二个纯源码checkout，从固定baseline fetch、固定依赖安装、现编共享库开始，按workflow原次序执行完整18组778测试、30条真实Scala/CHIRRTL命令，最后按同一工件glob收集131份IR及全部摘要/日志。此前不存在work；87个Maven依赖重新下载逐hash核验，HardFloat精确commit重新获取。全流程759.291秒，未扩大900秒预算；没有RTL/长数值重跑。实际收集204项、49,120,284 B，SHA `3fd7e75d951bf008f7fa593b7b31e70d1b0ce202b066213293d5297f8e631a8f`。
- 独立读回核对11源manifest、87依赖、30成功命令和131份IR；所有真实源码条目与旧df18相同，IR仅移除原审定来源位置后逐字相同。旧task_source字典误包含Python缓存，其中down的3项和seed的2项pyc hash不同；5个对应.py源hash均相同。原pyc字节未归档，不能进一步归因具体字段，因此保留差异而不宣称整个元数据字典相同。首次过强全字典比较失败也保留，未修改实际frontend门。独立核验摘要SHA `257c874ed11b22febbeb05ba39a4dfbb049600e1607ae258a69897797f3b6807`。
- done（局部）：冷源码完整顺序流程及工件核验。ongoing：本4文件修复发布与精确CI终态/工件闭环。75项M128执行源保持不变，数值策略/所有原FAIL保持。当前真实命令链仍是v0：相对官方BF16的第一差在n0，末y rel-L2约0.2682195；相对官方FP32末y rel-L2约0.0332366、cos约0.99944752，原开发门仍失败。隔离v2的改进不能转移为本链native通过；完整五block硬件验收保持OPEN。


### 2026-10-12 冷流程CI闭环与不改算术的内部观测

- 修复提交 `545226c1539d0488187df604a020301e4fd76137` 的 [frontend run38213042469](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/38213042469) 与 payload run38213042402 均SUCCESS。工件11729499931已下载核对48,455,609 B与SHA `19c2c6da7fd09bec3a22fa3d51c1f16ffa737fe3a0deed5af6675e8f34bbcdb4`；778 tests、30成功前端命令、11份源码清单、87依赖和131份与df18正规化一致IR逐项通过。独立验证摘要SHA `101968180df0f527d0b9ab50ae5e6f11bf6263d44a8f48715565860c151fa57a`。5项旧pyc差异及其对应源码相同分别记录。cefc/ce7两次旧基础设施失败保持原结论。
- 新 `scripts/observe_qwen2_attention_model.py` 在现有软件 Attention owner 上读取已计算的局部值，不替换owner或Scalar/Matrix。源绑定的CPython3.12 trace仅观察QK最终16分片、顺序和、实际因果score、exp/max/sum/inverse、进入PV的FP32/BF16 probability和最终PV packet；原75项执行源没有修改。观测器单独记录自身身份及已载入Python代码/默认参数/系数绑定；调用者仍须提供并验证Matrix库编译来源，它不自行证明ELF来源。
- 只在实际owner `response_fire` 接受成功、准确最终ACK字节和服务退休后封存。held success不算接受，错误ACK、reset或不完整观测不算成功；后续新事务不能追溯撤销已经接受的旧回执。future scores原路径未计算，原位保留缺失mask；PV各16列组重复8次的概率逐位核对并保留每坐标次数。外置诊断buffer不是新增硬件SRAM，不参与任何后续运算。
- 使用方法是在原驱动外层、原严格导入闭包之外导入该模块，再以 `AttentionObservation(existing_owner)` 的context包住现有驱动；接受Attention终态时自动停trace，后续FFN继续原路径。`save`可保全小实际激活、presence和次数文件以及摘要，禁止写入Git。新捕获必须有自己的source/input/工具身份，不继承旧M128数值PASS；本轮仅小synthetic门，不重跑M128、Chisel或RTL。
- 原v0公式和数值门均保持。采用官方BF16物化v2作为目标的询问尚未获答，当前4节点差异仍阻断；FP32模型比较、完整29节点门、真实carried prefill与五block硬件验收均未关闭。
- 新观测14测试通过，包含trace开/关所有实际服务握手及输出完全相同、独立整数舍入参考、真实响应改变、末ACK/错误/reset/held终态、源码/已载入函数及缺失/重复事件拒绝。独立纯源码checkout在显式获取固定baseline后，按现有model-contract工作流次序完成13+27+67+248+14=369测试及原解析模型摘要，68.268秒；只复用固定Python工具环境，未复制历史work或实值输入。首次准备因浅clone缺baseline在测试前停止，原失败保留；补精确fetch后续行成功。执行日志SHA `f96ef8260d6e6d94add7c6dfa9d330fe4f54c8e903674125a414fd29dbbf853d`。测试后仅补本文结果与状态表，执行源码、测试和workflow身份未变。
- 同次新编共享Matrix库SHA `22da518dc47e641cd7052b84d0c46389fd92d71665276fb671410cf5b994136c`，显式编译回执与源码逐项验证。synthetic M2捕获36个因果score、576个QK分片、72个normalizer字及3072个PV字；概率每坐标8次实际观察全部相同。所有被观察字段均经独立参考核对；future上三角缺失且不补值。完整握手trace SHA `d634b23f55d30131801a0f0d9814b004a14660be1f0713029cda87fc912a5e58`、实际输出SHA `8d7ae9c2688ea00bd1a46e7068daca70d746452c3edaab76fd202ada0026add3`；这是软件owner观测门，不是官方payload、整block或硬件数值通过。
- done（局部）：原545双CI及工件、只读内部观测和369项冷轻门；`c3645ea54bcee44e97443239c07967a559e0ef50` 已发布，model-contract run38217457589与payload run38217457594均成功。工件11733430538的261,855 B/SHA `9699ba4c3009541ba1463e934d89e42dcdf96ed14ff49d45d7c8cf228480290a`、5发布源、75执行源、92个已载入函数、3900实际word及presence/counts均独立核对，所有实际数据和握手与本地相同。CI共享库按自己的编译回执核验且ELF已保全，不声称不同环境的ELF相同。todo：后续获准数值策略接入时，同完整链保全实际内部观测；当前不为补观测重复长M128。

### 2026-10-12 公开三命令驱动的只读观测接线

- `execute_public_attention_observed` 直接包住原 `fullgraph_execution.execute_attention_owner`，绑定同一实际owner和原driver代码，返回原报告及已关闭的capture；不改变driver参数、握手和调度，也不调用completion、physical publish或finish。可传入未用capture以便原错误异常后检查不完整观测。原75项执行源码和算术均未改。
- 小门复用既有公开Command128 QK/Softmax/PV三命令M1合成fixture、同物理metadata/operand内存和原Matrix/Scalar；输入只有readonly Q/K/V，输出及两个虚拟区域均从哨兵开始。观测开/关的owner报告、所有Host计数和request/completion tick、完整Host事件digest、每次DDR写/ACK记录、每一公开边界快照及6144B实际输出完全相同。
- owner成功且最终ACK之后仍须接受原3个completion；PC0、PC1及背压均不允许物理读或publish。PC2接受后才允许physical publish，此时launch_result仅offered，原finish接受它是独立后续边界。虚拟scores/probabilities始终未写、未ACK、未发布；实际PV与写回逐字相同。owner级capture始终不宣称完整block或public launch通过。
- 额外检查实际Numerical错误、owner已成功但公开completion被扣住时发生local reset、复制job/断开的metadata map、错owner/reuse capture和被替换driver。真实reset与completion_ready同拍必须阻断公开成功；已接受的owner观测历史不会被追溯撤销。首次本地准备误指向另一冷checkout的共享库回执，被原严格路径守卫在0测试前拒绝；改为当前checkout现编0.5秒级host库，未放宽守卫。首轮5项小门通过，2.279秒，无RTL或M128。
- 独立review指出首次证据快照保留了Host报告的活动list引用；原直接边界断言及运算无误，但不能将首版工件当作各历史时刻的冻结快照。现改为即时deepcopy，并在执行结束后逐项断言历史completion长度0/1/2/3/3/3、Host允许发布0/0/0/1/1/1、物理已发布0/0/0/0/1/1及最终launch仅最后已接受。修正后5门2.294秒通过；初版日志/工件和发现记录保留。小路径共1973个Host模型tick，不能作为硬件周期或利用率。
- 修正后独立review无剩余阻断。新source-only checkout先获取精确baseline、现编共享host库，再按workflow原次序执行374测试（原369+公开接线5）和全部原解析摘要，69.621秒、EXIT0；4文件前后hash一致，日志SHA `037c676a6638872d30fa69140b041d7f411785c639db9bfd9ffcb42976af615d`。未复制历史work，只复用固定Python工具环境。本文在测试后追加结果，执行代码/测试/workflow保持冻结身份。
- done（局部）：原公开三命令路径、边界比较、独立review及source-only完整轻门；`c7c2b6fb9c35447f4b4318b06f0e38d2186920b3` 的 model-contract run38226081016/job114733805618 与 payload run38226080917 均成功。工件11735947380已核279181 B及SHA `6abcc9a32ab726677b8704b6694b25781ddb4dd1f4c13a755956bac997cd5bd5`，78项、374测试、4发布源、75执行源、92函数均核验。验证摘要SHA `d405ee0f5c070197565020fee6988d1583833bb52cabd429cd77b12e52b0dd5c`。跨host仅观测对象指针标识差异单列，不宣称原始日志逐字相同。
- 2026-10-12 10:50:23 UTC 用户批准按官方 BF16 舍入与中间精度修改完整链；[当前实现和数值边界](QWEN2_OFFICIAL_BF16_PUBLIC21_20261012_CN.md) 单独记录。原v0/native失败保留，逐节点门限不变；真实carried prefill及五block M128验收仍开放。
