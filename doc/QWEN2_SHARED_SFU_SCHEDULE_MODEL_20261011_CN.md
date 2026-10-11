# 固定16路SFU的跨批预约软件模型

首版新增 `scripts/qwen2_shared_sfu_schedule.py` 和对应测试；本次在同一模型中绑定原 divider 的源码时序。本模型没有实现硬件、没有运行RTL或整M128微步，也没有改变数值策略。C=1、C=2都是候选微控制器；C=1用于对照候选的串行执行，不是当前 `SiluVectorUnit` 的周期仿真。首版 wrapper 的 II21/38 是有意保留的较松下界，新的逐分支公式见后文。

## 原算术与资源

每lane保留原 `BlockScalarFloat` 内的一套单发 `HeteroFP32Alu`、一个独立单在途divider及转换器。没有使用core另外16路ALU，也没有把同一ALU内现有Add/Mul组合电路当作两个可独立发射的端口。

非饱和exp7逐节点执行：scale Mul、floor转换、fraction Add、七组独立RNE的Mul/Add、finish Mul。共17个ALU操作。SiLU另外执行denominator Add、reciprocal Div和三次Mul。因此每个非饱和元素为21次ALU、一次转换和一次Div。`abs(gate)>=80`保留原返回0分支；候选通过控制节点产生0，不计已被原分支丢弃的scale乘积。

实现复用现有矩形Attention模型的精确整数FP32 RNE工具做Add/Mul。Div仅使用普通FP32数值工具；测试从已冻结C++源码提取原add/mul/expneg并插入观测，对比每个节点和最终bits，包括±0、次正规数及80阈值。没有重写另一个exp近似。

## 周期与预约契约

默认divider latency和initiation interval均未绑定，返回 `TIMING_UNBOUND`，`scenario_cycles` 为空。手工同时给出两项，且单在途 interval≥latency 时，运行明确标注的合成 scenario；新增 `--source-divider-timing` 按每次操作数选择25/26拍，与手工参数互斥。两模式都只调度候选控制器。每个cycle的ALU/转换/control写在该cycle末生效，下一micro-op或输出握手下一cycle使用；新输入至少下一cycle才发第一步。

每lane每cycle只有一个context写口。Div返回优先占用，ALU当拍停止；无隐含返回队列、第二写口或免费重试。另一个context可以在前一个等待Div时使用ALU。Div请求保存batch、slot、generation、lane身份，返回逐一校验。现有寄存器的代次由软件断言追踪，防止context提前释放或串标签。

输出按原batch顺序提供，保持到ready；已offer的context只在输出握手后释放。后一个context发生错误时，已提供但被背压的前一个输出仍保持valid/payload，之后握手只记入 `output_drains`，不计入成功结果。若ready永远为false，模型明确停在未完成scenario而不是撤销该offer。没有DDR写或AXI ACK模型，因此 `all_outputs_acknowledged=null`，`all_output_handshakes_completed`只描述内部结果端口。发生注入错误后停止新请求、排空已接受Div及预约冷却时间，再释放其他取消的context并返回错误；之前已经握手的结果仍列为已发生的内部暂存副作用，不冒充整请求成功。

`predicted_full_block_cycles`、`measured_cycles`及`rtl_measured_cycles`始终为空。scenario的ALU一步一cycle仅描述此候选资源日历，不是800MHz或任何频率的时序证明。最多64个合成向量组；CLI拒绝整M128规模。

## 数值flags边界

本模型没有完整HardFloat flags计算，因此自动数值接受与旧Scalar错误策略验证始终为false；未注入的原始flags记为null，不能把有限结果当成旧Scalar接受。

独立注入的flags用于验证政策路由：外部Add/Mul/Div仍拒绝NV/DZ/OF/UF，NX单独接受；原ExpNegative内部flags仍不自动上升为错误。另有独立错误及Div坏标签注入。该错误路径测试不等于自然产生的HardFloat flags已证明。非有限输入在接受前显式拒绝；数值工具不支持的中间结果域（如overflow）导致 `DIAGNOSTIC_DOMAIN_REJECTED_DRAINED`，仍排空已接受操作，但不捏造结果bits或HardFloat flags。

## 新增状态和路由

候选每lane/context显式预算181bits：gate/up/fraction/work0/work1五个FP32，k8，micro-PC5，valid/error，flags5和flags-valid。context0拟覆盖外层gate/up及原core fraction/Horner/product/k/PC等寄存器。该覆盖是设计约束，没有通过综合证明。

| 逻辑状态增量 | C=1 | C=2 |
|---|---:|---:|
| 额外context | 0 | 2896bits |
| 额外batch ordinal | 0 | 20bits |
| Div owner valid/tag | 16bits | 32bits |
| 已offer输出valid | 1bit | 1bit |
| 已offer输出context index | 0bits | 1bit |
| 合计新增逻辑寄存器 | 17bits | 2950bits |

不另算Div结果暂存，因为采用返回优先的单写口仲裁。真实Div tag仅为context index加valid；batch、generation、lane是软件断言身份，不冒充已计入的物理tag位数。`waiting_divider`由owner valid/context及micro-PC导出，不额外复制一个未记账的context bit。已offer payload仍在原context的结果寄存器中，软件报告的payload快照不是新硬件队列。新增ALU操作数选择、context寻址、返回tag及回写选择逻辑没有面积/布线验收。没有把 `OverlappedSilu` 原两项输入/输出队列同时当成免费context空间；原内存队列未纳入本组件。

## 接入整层模型

入口为 `schedule_silu(gates, ups, contexts=1|2, divider_timing=...)`，输入为 `[groups][16]` 原始FP32 uint32 bits。返回profile_kind=`candidate_context_schedule`、源码pins、scenario_cycles、peak_contexts、output_count、scope以及半开区间 `reservations`，资源名为 `silu.alu.00`、`silu.divider.00`等。

整层日历必须显式选择该候选profile，并另外预约输入/输出、存储与ACK；不能将它的吞吐替换默认现wrapper，也不能与另一owner重复占有同16路SFU。整层报告只引入这份时序来源元数据，不用它自动填满 owner-level 服务时间。

验证命令：

```sh
/workspace/shared/hetero-contracts-venv/bin/python -m pytest -q tests/test_qwen2_shared_sfu_schedule.py
python scripts/qwen2_shared_sfu_schedule.py --contexts 2
python scripts/qwen2_shared_sfu_schedule.py --contexts 2 --groups 2 --divider-latency 12 --divider-ii 13
```

最后一行的12/13是明确的合成预约条件，不是实际divider参数。测试覆盖逐节点bits、排他资源、Div与ALU写回竞争、背压持有、context/tag生命周期、注入错误不再发布、最终结果和资源排空。


## 2026-10-11：绑定原 HardFloat 时序

固定 HardFloat commit 为 `c1105e6ac6a0dd90fc80893efc4830ab609005d3`，
`DivSqrtRecFN_small.scala` SHA256 为
`905b3c0b4b47286d56b7f7d37a2886add7fd662336f5864df454680021e92da9`。
已只读取得并比对原 capture receipt，连同输入转换和组合 rounding 源码复核；
`timing_binding()` 每次检查本地准备脚本、算术/控制源码及历史源哈希回执。
CI 不下载或构建 HardFloat。

以请求在 edge0 握手为准，寄存 valid 在 edge k 后可见，最早 edge k+1 握手。

| 资源/请求 | 结果首次握手 | 下一请求最早握手 | 条件 |
|---|---:|---:|---|
| 裸 divider | D | D | D25 或 D26；outValid 与 inReady 可同拍 |
| BlockScalar Add/Mul | 2 | 3 | 连续 ready、无异常中断 |
| BlockScalar ExpNegative | 2 或19 | 3 或20 | 饱和 / 非饱和 |
| BlockScalar Div | D+2 | D+3 | 含 divIssue 和结果寄存边界 |

D25 条件为正规化 significand(a)≥significand(b)，否则 D26；不能比较整个
浮点数大小或指数。当前软件 classifier 只接受有限、非零、正规 FP32，
其他域明确拒绝。SiLU 的 a=1，b=1 或2时为 D25，1<b<2 为 D26。
裸 divider 没有 result-ready，必须保留返回捕获端口；候选允许旧结果采样与
新除法请求同边沿，仍只有一个 lane 写口。

现 `SiluVectorUnit` 六阶段串行，成功组 II=`45+17*B+Q`，
B 表示组内任一路非饱和，Q 表示任一路 D26。N组从首次输入到末次输出握手的
边沿差是 `45*N+17*L+Qsum-1`。这些是现控制器的源码公式，C1/C2候选日历不
冒充该控制器。owner 的 calc/resume、load/store/ACK 另有开销；例如 core
直接 Add 链和 Norm reduce 链的请求间隔分别至少4、5拍，不能一律填3拍。

### 已保全 M128 输入的分支检查

只读复用了三份 gate：原 v0 cold128、诊断 v2 cold128 和 carried128(P128)。
先核原 receipt、字节数和SHA。v2 BF16可表示输入先去重，只计算2156/2106个
绝对值的原 exp7 与 denominator；v0 FP32输入采用显式逐节点 FP32 add/mul，
全量节点检查 normal/zero，66个索引的1254个节点再与独立整数RNE核对，
检查宿主 FE_TONEAREST。没有执行 reciprocal、完整SiLU、完整block或RTL。

三份都为1146880次D26、71680个非饱和组。原 wrapper 算术边沿差下界
4,515,839；同16个原单在途divider的服务下界为26×71680=1,863,680。
后者即使允许理想调度/无限context也不能消除，但该理想化只用于下界，
并未给实现免费增加context。

| 输入 | 有用 MAC | 仅 divider 服务的乐观利用率上界 | 原wrapper+理想Dense上界 |
|---|---:|---:|---:|
| v0/v2 cold128，P0 | 6014828544 | 78.793784% | 24.564014% |
| v2 carried128，P128 | 6065160192 | 79.453125% | 24.769563% |

分母固定4096×完整周期。Dense下界是1462272拍；不把全部有用MAC/4096的
1468464拍误称Dense。其余成本都未计入，因此这些是乐观上界，不能称预测
或实测利用率。原21N+17L−1及2723839拍只是较松的v1下界，保留其版本，
没有悄悄改写旧报告。M1024及其他prefix尚未检查分支分布，不能推广结论。

在这些输入上，仅增加context不够达到80%目标。改divider吞吐、增加流水/
端口、重用别的已占用单元或改reciprocal算法，都需要明确的新控制/寄存器/
组合路径/资源所有权与数值证明；不能算免费优化，也未修改固定资源。

复现小门（没有权重、Chisel或RTL）：

```sh
python scripts/qwen2_shared_sfu_schedule.py --source-timing-audit
python scripts/qwen2_shared_sfu_schedule.py --contexts 2 --groups 2 --source-divider-timing
python scripts/qwen2_shared_sfu_schedule.py --gate-result /path/to/cold/RESULT.json
```

原 v0 复现脚本及三份紧凑摘要在
[QWEN2_SFU_TIMING_20261011](../reports/execution/QWEN2_SFU_TIMING_20261011/README.md)。
flags、完整时序、数值验收和RTL校准保持未完成。

## 后续模型候选：上游两位除法选项

固定上游 `common.scala` 定义 `divSqrtOpt_twoBitsPerCycle=16`。现硬件
`BlockFloat.scala` 仍实例化 `(8,24,0)`；软件候选显式指定16，没有更改该配置。
该选项使正常除法计数26→24→…→2→1，edge13后结果可见，edge14采样且可
接收下一请求。它保持最终RNE rounder及接口，却启用第二个依赖试减、比较
和选择步骤。divider实例仍16个，并不代表组合电路面积/关键路径不变。

纯整数递推模型的范围刻意限定为：输入正规且有限非零、精确商正规、舍入
结果正规。只建模该域内的RNE结果和NX；零、次正规、非有限、UF/OF等范围
拒绝。例如 `00ffffff / 40000000` 的精确商指数为−127，虽然RNE会得到最小
正规数 `00800000`，此接口仍必须拒绝。不能将这项窄域结果当成完整HardFloat
flags、sqrt或整个SiLU异常政策的证明。

人工不变式审查：令A、B为24-bit正规化有效数，处理n个小数位后
`P_n=floor(A*2^n/B)`、`R_n=2*(A*2^n-B*P_n)`、`S_n=P_n*2^(25-n)`。
始终 `0≤R_n<2B<2^25`，所以26-bit余数与第二步的27-bit截断不丢有效值。
两位路径恰合成两个相同恢复除法步骤，sticky保持 `R_n!=0`。一位路径在
A≥B时n=24结束，其他一位及两位在n=25结束；额外低位与余数并入sticky后
产生相同RNE/NX。指数、符号及normal打包另行对照独立有理数divmod量化器。
这是针对软件源码翻译的数学审查，未做形式验证或RTL等价检查。

首个原型及已集成的8592个确定用例中，7463个域内输出/NX在两种配置与独立
量化器之间一致，1129个域外拒绝。95266个相同精度边界的商/余数/sticky
逐字段一致；770个最终raw商的低位确实不同，RNE/NX仍相同。量化器独立于
递推/GRS算法，但共享解码与域规则，不能称三套完全独立实现。

当前单写口候选对每个非饱和元素仍需21次ALU、一次转换和一次Div结果写入，
必要写口服务为23N。即便D14，cold128单独这项仍把全层乐观上界限制到
89.071234%；它没有建立完整80%或90%可行方案。新增返回写路径、双发射或
借core算术都须显式计端口、状态、路由、所有权和被挤占工作，不能免费假定。
下一优先回到完整DAG驻留/外部流量/owner并行条件，不连续以局部SFU吞吐
代替完整prefill验收。

本次集成保留options0默认值，options16必须显式启用source模式；58项小门
已通过，覆盖逐位递推、正常域NX、拒绝边界、返回背压、同拍接收、poison及
资源账。source模式不再调用宿主浮点除法，合成时序模式保留原参考。
全局flags仍未生成；只有该normal域divider的NX有诊断值，不能据此关闭
完整SiLU异常或数值门。以下入口仅运行两个group的软件候选：

```sh
python scripts/qwen2_shared_sfu_schedule.py --contexts 2 --source-divider-timing --source-divider-options 16
```
