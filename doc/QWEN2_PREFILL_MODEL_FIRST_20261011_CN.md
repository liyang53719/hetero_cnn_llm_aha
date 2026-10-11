# 三模型五个完整 block：先验证模型与 prefill

2026-10-11 起的执行顺序是 Qwen2-1.5B layer0，然后 Qwen3.5-0.8B
layer0 / layer3，再到 Qwen3.5-35B-A3B layer0 / layer3。先用同一批真实输入
在软件模型中验证完整 128-token prefill，再进行更长输入和冻结激励的硬件回放。
M16 只作早期诊断，不代替 M128；逐次 M1 launch 不称为一次 prefill chunk。

## 已有证据及边界

| 完整 block | 已有实际范围 | 尚缺的主要闭环 |
|---|---|---|
| Qwen2-1.5B L0 | 合成权重、真实 H1536/F8960 的完整 15 阶段 M16；另有 Matrix4096/iDMA 双层连续合成回归 | 固定官方权重/embedding 的 M128 软件模型已执行但未过完整数值门；原硬件算术与官方差异待修；真实 M128 完整硬件 |
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
