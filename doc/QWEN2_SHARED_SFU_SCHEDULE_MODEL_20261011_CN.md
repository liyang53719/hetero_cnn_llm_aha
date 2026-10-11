# 固定16路SFU的跨批预约软件模型

本增量只新增 `scripts/qwen2_shared_sfu_schedule.py` 和对应测试。本模型没有实现硬件、没有运行RTL或整M128微步，也没有改变数值策略。C=1、C=2都是候选微控制器；C=1用于对照候选的串行执行，不是当前 `SiluVectorUnit` 的周期仿真。当前wrapper的II21/38下界仍另列成立。

## 原算术与资源

每lane保留原 `BlockScalarFloat` 内的一套单发 `HeteroFP32Alu`、一个独立单在途divider及转换器。没有使用core另外16路ALU，也没有把同一ALU内现有Add/Mul组合电路当作两个可独立发射的端口。

非饱和exp7逐节点执行：scale Mul、floor转换、fraction Add、七组独立RNE的Mul/Add、finish Mul。共17个ALU操作。SiLU另外执行denominator Add、reciprocal Div和三次Mul。因此每个非饱和元素为21次ALU、一次转换和一次Div。`abs(gate)>=80`保留原返回0分支；候选通过控制节点产生0，不计已被原分支丢弃的scale乘积。

实现复用现有矩形Attention模型的精确整数FP32 RNE工具做Add/Mul。Div仅使用普通FP32数值工具；测试从已冻结C++源码提取原add/mul/expneg并插入观测，对比每个节点和最终bits，包括±0、次正规数及80阈值。没有重写另一个exp近似。

## 周期与预约契约

默认divider latency和initiation interval均未绑定，返回 `TIMING_UNBOUND`，`scenario_cycles` 为空。只有两项都显式给出，且单在途要求interval≥latency时，才运行小合成scenario。每个cycle的ALU/转换/control写在该cycle末生效，下一micro-op或输出握手下一cycle使用；新输入至少下一cycle才发第一步。

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

整层日历必须显式选择该候选profile，并另外预约输入/输出、存储与ACK；不能将它的吞吐替换默认现wrapper，也不能与另一owner重复占有同16路SFU。本增量不改整层日历文件。

验证命令：

```sh
/workspace/shared/hetero-contracts-venv/bin/python -m pytest -q tests/test_qwen2_shared_sfu_schedule.py
python scripts/qwen2_shared_sfu_schedule.py --contexts 2
python scripts/qwen2_shared_sfu_schedule.py --contexts 2 --groups 2 --divider-latency 12 --divider-ii 13
```

最后一行的12/13是明确的合成预约条件，不是实际divider参数。测试覆盖逐节点bits、排他资源、Div与ALU写回竞争、背压持有、context/tag生命周期、注入错误不再发布、最终结果和资源排空。
