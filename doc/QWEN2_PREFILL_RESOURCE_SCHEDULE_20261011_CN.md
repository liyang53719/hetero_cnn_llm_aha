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
