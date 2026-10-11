# Qwen2完整预填充：共享资源预约模型

当前完成的是软件预约器与数据生命周期检查。可信的完整block周期模型仍为
**OPEN**；没有生成Chisel、运行RTL/EDA、下载模型权重或改变数值策略。

实现与测试：

- [预约模型](../scripts/qwen2_prefill_resource_schedule.py)
- [专项测试](../tests/test_qwen2_prefill_resource_schedule.py)
- [矩形Attention模型](../scripts/qwen2_rectangular_attention_model.py)
- [原Host流量/请求下界](../scripts/qwen2_prefill_traffic_bound.py)

## 完整DAG与默认边界

模型覆盖Qwen2-1.5B、batch=1、cold prefill M128/M1024。21个public stages
按实际依赖顺序保留：

input_norm → Q → Q_bias → Q_rope → K → K_bias → K_rope → V → V_bias →
KV_append → QK → softmax → PV → O → attention_residual → post_norm →
gate → up → SiLU_mul → down → residual。

QK/softmax/PV使用已发布Attention迭代器并作为一个融合owner，故共有19次owner
执行；3个命令的admission在Attention算术前，输出ACK后才发布融合结果。
每个消费者必须见到已提交的生产者。所有末尾写ACK、owner排空与终端Host fence
都在模型中，不能以写请求已发出代替完成。

默认是无重叠的保守基线：沿用现Dense行组/权重重读，Attention用候选矩形路由，
其他owner保持原算术请求和读写顺序。它不是现有Chisel逐拍执行轨迹，也未实现
Attention所需的SRAM lease/gather/capture硬件。

## 固定资源与生命周期

| 资源 | 模型中的原有边界 |
|---|---|
| Dense A SRAM | 16 banks×1376×32 B，704,512 B |
| Dense B SRAM | 16 banks×160×32 B，81,920 B |
| Matrix | 16×256，4096 MAC，5 contexts，8 metadata slots |
| Matrix结果 | 原两项wide FIFO；Dense另有一份16 KiB finalValue |
| core SharedL2 | 16×128-bit banks，四bank为一个仲裁组，573,440 B |
| elementwise SharedL2 | 独立原实例，12,288 B |
| 算术 | core单Scalar、core16 ALU、elementwise原16 ALU、唯一SiLU16 Scalar lanes |
| 外部接口 | 一个共享IDMA事务归属；读提交与写B ACK必须等待 |

VectorSilu与OverlappedSilu是编译时二选一，不是额外32条SFU。当前SiLU没有供
Attention自由调用的raw primitive接口，未来generic/multi-context候选未接入本基线。

- Dense A按源码80行（K1536）或32行（K8960）分组；实际尾组和N contexts保持
  至多5个物理contexts。K按16递增，权重读字节与原流量模型逐项核对。
- B地址是 `halfBase + depthWithin16*5 + ctxN`，半区base为0/80。
  因此nt=1的16个有效word也跨到word75，不能当成16个连续word的物理占用。
  本基线一次只用一个完整80word/bank半区，预留40,960 B；payload仍按有效
  `16*nt` words计DDR流量，另列high-water `15*5+nt`。没有免费重用地址空洞。
- Dense最后K的每个context先返回、捕获到原finalValue、写出并等ACK，再继续
  下一context，避免虚构可同时保存五份wide结果的缓冲。
- Attention独占借用同一A/B实例；QK partial槽归约后才释放，PV在返回key=query
  时捕获对应行，输出ACK后释放。1/5-context均受原容量和metadata限制。
- Norm仅保留当前FP32行与原寄存器；elementwise以1024元素的A/B/C tile顺序
  load→compute→store/ACK；KV依次复制K、V。SiLU顺序为gate读、up读、原六阶段
  wrapper、写与ACK。没有借用独立SRAM实例的空闲容量。

资源预约保守排斥同一bank读/写，并关闭所有未经证明的重叠。Dense双缓冲和
OverlappedSiLU现有重叠能力暂不记收益。重复宏保留内部操作次序，验证一次迭代
前后所有权一致后重复；这不是把完整owner的下界伪装成细粒度时序。

## 未绑定参数与结果口径

默认21类timing参数全部未绑定，主要包括：

- DDR每64 B服务、读提交及写ACK等待；具体AXI burst、root对齐和背压未展开
- Matrix issue/返回等待、命令开始/排空
- bank/fabric访问及仲裁等待
- Scalar Add/Mul/Exp/Div/Sqrt、Vector和完整SiLU group服务时间
- owner切换、Host descriptor/policy admission、最终fence

descriptor/tensor/policy具体取数与字节量仍为opaque admission，未计入报告的
tensor/parameter传输字节。各owner内部FSM、异常/取消/重试/错误排空、数值与
flags尚未执行。Scalar原underflow/error策略必须保留；这里没有另写数值算术。

首版较松的源码下界以 `v1_loose_wrapper_bounds_preserved` 保留：Scalar Add/Mul请求II≥3，Exp饱和/非饱和
II≥3/20，当时 Div 的 FSM 下界≥4，未绑定实际 divider 延迟。原SiLU16 group II下界为
21或38，取决于是否有lane走非饱和exp；没有把六个primitive请求算成六拍。
本预约器未读取实际gate数组，也不将这些下界当成实测服务时间。

`--synthetic-profile`只给预约器测试绑定一组明确的假设。其结果名称是
`synthetic_scheduled_cycles`，仅用来核对预约、重复宏与生命周期；不得解读为
性能预测、实测周期或利用率。默认该字段也为null。所有模式的canonical
`predicted_full_block_cycles`、`rtl_measured_cycles`、`rtl_measured_utilization`
始终为null。

## 已验证层级与下一步

专项Python测试验证了：完整19-owner/21-stage次序；M128/M1024 useful MAC分别
6,014,828,544与49,527,914,496；Dense权重读分别242,221,056 B与1,739,587,584 B；
Attention原迭代器计数；Norm/RoPE/bias/residual/SiLU请求数；bank/context/结果槽
容量；重复宏；同资源双预约、提前释放、未提交依赖、缺末ACK及缺终端fence的拒绝。
这只验证该软件预约器，**不构成Chisel真实死锁或数值正确性证明**。

源码依赖由39个SHA256 pins绑定；漂移需重新审计。调用示例：

```sh
python scripts/qwen2_prefill_resource_schedule.py --tokens 128 --out /tmp/m128-unbound.json
python scripts/qwen2_prefill_resource_schedule.py --tokens 1024 --contexts 5 --out /tmp/m1024-unbound.json
python scripts/qwen2_prefill_resource_schedule.py --tokens 128 --synthetic-profile --out /tmp/m128-scenario.json
python -m pytest tests/test_qwen2_prefill_resource_schedule.py
```

下一步是在同一模型中逐项绑定有证据的服务时间、接口及背压规则，补齐Host
metadata流量与实际FSM转换，再针对明确bank/缓冲所有权逐项开放重叠。SFU候选
需先保持独立证据层级，不能直接给默认基线免费pipeline收益。完成这些工作之前，
可信完整周期模型与性能验收均保持OPEN。

## 2026-10-11 CI 序列化复核

提交 `a17ebcc91cd3ffdd38e42743aa3264ea25d75f0c` 的轻量模型 CI 实跑
168 项测试通过；14 份 JSON 的源码 pins 均通过核验。13 份报告逐字节相同，
`m128_resource_synthetic.json` 的 4 个预约样本存在集合遍历顺序差异。
每个资源集合、周期、事件及其余字段相同；原始 byte-equivalence 失败记录保留，
不能将它写成全部报告逐字节一致。

修正只在 `ReservationBook.reserve` 中将同时占用的资源名称排序。预约的成员、
持续时间、冲突检查和释放顺序语义均不改变。新增独立 Python 进程的
`PYTHONHASHSEED=1/713` 回归检查序列化字节和开始/结束周期一致。这不是
数值或硬件调度优化；后续 CI 仍需核验新报告的实际字节一致性。


## 源码时序元数据的增量

报告schema升级为2，新增 `known_sfu_source_timing`：绑定原HardFloat的
D25/D26分类、同边沿返回/新接收、Scalar D+3、SiLU六阶段公式及适用域。
复用[共享SFU模型](QWEN2_SHARED_SFU_SCHEDULE_MODEL_20261011_CN.md)的同一
函数，并把该函数源码/原准备脚本/历史HardFloat源哈希receipt纳入pins。

完整DAG的21类宏服务参数仍全部unbound；Scalar core占用不等于owner请求
间隔，当前宏未展开calc/resume、真实branch数量和内存ACK。没有把局部时序
公式填进完整预测，也不让合成日历改名为实际硬件周期。新增回归明确验证
元数据已绑定而 full-block prediction/RTL measured 仍为null。

## 原 Host 完整界的版本化收紧

新增独立 `--observed-silu-host-bound` 入口，固定使用已提交原 v0 cold128
gate 审计的SHA。它描述当前原Host mapping，不是上面的矩形Attention候选
日历，也不允许M1024、contexts5或合成时间profile。历史Python producer
及审计身份原样保留；当前owner/算术/上游源码仍须匹配。

旧完整下界9127424包含一次SiLU最松项430080。新证据只替换这个项：

| 项目 | 原界v1 | 保存输入条件下的v2 |
|---|---:|---:|
| 当前Dense下界 | 3784704 | 3784704 |
| 其他非Dense下界 | 4912640 | 4912640 |
| SiLU下界 | 430080 | 4515839 |
| 完整成功请求下界 | 9127424 | 13213183 |
| 固定4096分母的有用MAC上界 | 16.088482% | 11.113628% |

这是条件界：实际SFU输入必须满足该保存软件gate的分支统计，原flags策略
允许全部阶段成功，owners继续串行；尚未证明真实Host已生成相同gate。
新的边沿差内部已包含exp微步、除法和wrapper握手，不能再叠加旧430080
或另加1863680除法服务量。load/store/ACK及首尾控制仍未计，所以不是精确
owner时间。旧v1保留，并没有为新代码重新绑定旧PASS。

只算SiLU+理想Dense得到的24.564014%是遗漏其他owner的更松局部上界，不能
替换完整mapping上界。原divider单项78.793784%同理。真正完整周期预测与
RTL实测字段仍为空。

```sh
python scripts/qwen2_prefill_resource_schedule.py --observed-silu-host-bound
```

## 下一步优先级：完整数据流，停止局部吞吐外推

cold M128达到80%/90%的完整周期预算分别为1835580/1631626。当前Host
owners串行，除SiLU外的非Dense下界4912640中，Attention占4360704，
Norm/bias/RoPE/residual占551936。因此局部D14并不解决整层目标：

| 条件，仅替换原SiLU项 | SiLU下界 | 全层下界 | 有用MAC上界 |
|---|---:|---:|---:|
| D26原wrapper及保存gate分支 | 4515839 | 13213183 | 11.11363% |
| 未实现D14，保持原wrapper | 3655679 | 12353023 | 11.88749% |
| 未实现D14+C2，只取23N单写口floor | 1648640 | 10345984 | 14.19357% |
| 反事实SiLU免费 | 0 | 8697344 | 16.88405% |

后三行是条件分析。再把Dense理想化至1462272拍且SiLU免费，仍有6374912拍、
23.03505%上界。此表不适用于改变了Attention映射的矩形候选。

[驻留方案账本](QWEN2_PREFILL_RESIDENCY_AUDIT_20261011_CN.md)的
KC256/Ntile256/768KiB候选也有独立障碍：BF16权重一次93585408B、外部
FP32 A32243712B、FP32 D11796480B，合计137625600B。原iDMA一次一个
事务且读写互斥，64B/cycle单此流量至少2150400拍，有用MAC上界68.28795%。
仅读流量125829120B也需1966080拍，上界74.68994%；仅允许读写重叠不够。
这些字节依赖明确的候选驻留条件，没有给模型免费添加端口或更改数据精度。

下一步沿既有21阶段DAG核对各边的外部字节、FP32值驻留/转发、bank端口、
缓冲生命周期及最终ACK，并检查矩形Attention仍占用的单Scalar归约。
该候选当前2082048次Scalar请求本身已超过80%预算；共享现有Vector需列明
所有权和被挤占工作。当前Matrix尚无FP32 accumulator seed接口，分K保存/
恢复不能用分块求和替代原FMA顺序。外部改BF16、改归约或近似reciprocal
会改变数值合同，不能当作本轮已批准或无成本收益。

## 同一全DAG中的 resident_m128_nc3 候选

通过 `--dense-mapping resident_m128_nc3` 显式选择，默认仍为current。
该候选只支持cold M128，并沿原19-owner/21阶段执行；没有跨owner并发或
同源A转发。Dense使用前述1024/512 words分区，七矩阵全部纳入容量与流量
计数，Attention沿同一Scratch对象地址且验证候选分区高水位。

每个C prefix以实际bank word地址绑定逻辑M/N与已完成K。缺seed恢复、丢掉
最后一拍FMA、地址别名、越界行、提早复用context/C、缺写ACK，均有拒绝
回归。只保留现5contexts、8metadata、2结果FIFO和1finalValue；结果逐tile
保存/写回后才复用，不免费缓存五份完整返回。两半B物理容量都保留，但本
保守日历只声明串行填充一半，没有偷算预取并行。

软件事件运行覆盖有用MAC6014828544，Dense wide issues1462272，partial
恢复/保存各81788928B；外部读128188416B、写22544384B均计ACK，完成全部
19 owners。计数模型不执行权重算术，数值/flags/RTL门仍未完成。

新增资源下界从该完整事件图提取，各独立资源只给每请求至少1拍，再对每个
owner取max、串行owners求和。该图外部iDMA单项至少2355200拍，Scalar
请求单项至少2476288拍；按owner依赖相加至少4944128拍，固定4096分母的
有用MAC乐观上界29.701173%。它与原Host的11.113628%条件界属于不同映射，
不可直接当作实测提速。新界尚未套入实际D26/exp时延、bank等待、partial
路由、真实FMA反馈、命令字节或DDR延迟，真实周期不会因此已经可信。

```sh
python scripts/qwen2_prefill_resource_schedule.py --tokens 128 --contexts 5 --dense-mapping resident_m128_nc3
```

首次独立审查发现模型可漏掉seed操作、可把逻辑行改成128而不拒绝。修正后
显式绑定shape、C物理地址、seed-ready及255+1连续K步骤，完整tile集合必须
闭合，新增负例保留。当前小门18项通过；完整CI以新精确提交另验。

## 驻留方案的实际数值执行

后续[数值证据](../reports/execution/QWEN2_DENSE_RESIDENCY_NUMERIC_20261011/README.md)
将同一分区落实成普通C++的真实768KiB bank数组，而非只累加事件。仅替换原
Dense函数，实际搬运BF16 A/B、保存/读取FP32前缀并逐lane保持递增K顺序。
固定官方L0权重的cold M16/M128全部15阶段与原v0逐字节一致，M128覆盖
5308416值。七个Dense的A/W/D分别为13893632/93585408/11796480B，partial
每方向81788928B；五上下文和三C槽路径均实际执行。

这是软件地址/算术等价门。原Host、物理seed接口、端口时序和异常flags没有
因此通过；原官方精度FAIL与完整时序unbound保持。29.701173%仍为上述事件图
的宽松上界，数值CPU耗时不用于硬件周期或利用率。

矩形Attention也已在同一软件block中执行真实bank值：M128的Q/K/V、score、prob
占A/C168words/bank，五条带partials占B160words/bank，PV捕获仅在条带排空后
复用B。每行以causal最后有效K的实际返回值捕获，避免后续零概率改变负零；
返回tag到行捕获的路由仍是未实现硬件接口。15阶段全bit等于原v0，原精度FAIL
保持。[实际计数与范围](../reports/execution/QWEN2_RECTANGULAR_NUMERIC_20261011/README.md)
不提供新的时钟预测或RTL利用率，现有宽松下界也未被软件CPU耗时替代。

## 从模型到最小接口的资源检查

[Chisel前端候选](../candidates/qwen2_resident_matrix/README.md) 已对实际生产
service的可选return-tag补丁做编译/CHIRRTL检查，默认0的IR保持相同。启用16-bit
tag声明增加160bit存储（原8 metadata＋2 result深度不变），仍8个retained
endpoint和8个ICG声明。未实例化的seed控制器有138bit状态，无payload寄存器。
这些是前端声明计数，物理面积/时序未测；没有改变固定4096 MAC/拍分母。

Seed完整context为256个512-bit beat。现有256-bit行bank每个active beat要
两次同bank read；M128 Dense已知81,788,928B恢复量对应1,277,952 beat与
2,555,904 read事件。最小owner还需至少512-bit assembly/skid、phase/address/
identity控制及实际bank写口mux/valid/clock路由。它们尚未实现/绑定，不计为免费。
两个read事件不自动等于两个全局周期，跨bank重叠与端口时延需组合后证明。
因此29.701173%旧事件图宽松上界未被冒称新实现的可行预测或实测。

## 真实bank读源的局部控制成本

前述“两次读不等于两周期”现已在真实Chisel读源结构及软件控制模型中落实：
同bank低/高word相邻发起，随后组装并提交，单缓冲FSM每个有效beat占4拍。
完整16×256的256beats/512reads在无停顿小模型中共1030拍；它包含6个setup/
terminal拍，leaf ACK为明确软件握手模型，不能冒称RTL测量。40个offer停顿
精确增加40拍。partial M3/N48为64beats、18reads、152拍，不读padding哨兵。

原M128驻留方案的1,277,952个restore beats，若使用此保守源FSM，则仅读/提交
路径小计5,111,808拍，尚未加acquire、保存、Matrix、DMA或其他owner。既有
29.701173%是旧事件图每请求至少1拍的宽松上界，不是本实现的可行预测。
这个差距必须进入布局选择，不能把seed接口或两次读当作免费。

实际StreamingDense hook保持A1376/B160word配置，每bank单read/write且默认
关闭；独立组合仅实例化候选A/C1024word部分，尚未安装B512或owner lease表。
reader720bit＋读mux5bit＋既有controller138bit＋组合legacy pending1bit合864bit。
这不是新增864bit物理综合结果；其中既有状态与外部owner/leaf成本明确分列，
布线和bank选择mux的面积/时序未知，固定4096分母不变。

下一步用相同K/FMA/偏置/异常合同比较M128转置映射：必须核算A广播分组、每个
bank的真实读写口、K8960容量/重读以及全19-owner流量，不能只看Dense发射饱和度。
在模型有证据前不启用资源重分区、不增阵列，也不宣称80%可达。
