# 35B 同次真实前缀 → 32 头 chunk 接线与数值诊断

## 当前范围

- 已发布依赖：831d9cbb 显式渐进下溢指数策略，三条原 CI 及工件已独立闭环。
- 本批从同一次实际 RMS → QKV → Conv 和 RMS → A/B → ACK 重排 → Prep 接入 chunk64。
- 必须使用同一个 TypedMemory 中已发布、完整写入及 ACK 的 Prep MemoryRegion，同一个 GateScalar 和 Vector16。不得把留存 raw 再导入为生产者。
- 全部 32 个 value head，key/value 维度均 128；先 M16（真实16 token，chunk 内补48零），后 M128（真实128 token，两个 chunk）。
- Conv history、chunk output/state/scratch 均保持未发布 staging，不推进 generation。尚无最终 block 联合提交。

## 有界执行与容量

- M16 无停顿 transport 预测 24,046,593 步，watchdog 加 1,024 步；M128 48,123,905 步加 1,024。旧20M上限不适用。
- wall deadline 独立最多1800秒；每100万步保存进度。超时保存真实 output/state/scratch、已写/已ACK覆盖和物理 pending，不自动 drain，不声称可恢复。
- state 每副本2MiB；scratch M16 27,918,336 B、M128 53,739,520 B。DDR容量显式增加。
- 软件 transport ticks 不包含硬件算术时延。Vector16 Mul→Add 是两次FP32舍入，不能计作FMA；硬件完整周期、MAC利用率、占空比未知。
- generator 跨 yield 的局部列表及总硬件寄存器驻留上界仍未证明。现有标量/向量资源身份不等于完整硬件映射验收。

## 参考与门禁

- 官方35B固定源码中，在 Q/K 归一化和 Q 缩放之后提取未修改 chunk suffix，保持实际32头 shape/stride，避免重复归一化。
- 原上游 RMS/QKV/Conv/A/B 数值门保持。Prep Q/K/V/beta 精确与 g 诊断分别记录。
- 当前同输入 chunk 仅逐输出及完整FP32 state诊断，未另行批准 standalone 误差门，不自行设置 PASS。
- 完整 block 数值、MoE、最终状态联合提交、生产 Chisel/RTL、目标90%利用率继续 open。

## todo / ongoing / done

- done：整数 transport 公式与缩维真实读写计数交叉验证；全维首ACK错误drain、带物理pending写超时保留、producer拒绝等12项运行前小测。
- done：固定官方 suffix 纯函数；同次真实 M16、M128；80源/10native及全部raw独审。
- done：最终冷回归557项/54套/164源，零skip且前后不变；官方固定runtime smoke3项。
- ongoing：小批发布、精确CI及原始工件核验。
- todo：Z投影校准、32头gatednorm、O投影及MoE完整block接线。

## M16 已完成的实际证据

- 同次八个 owner terminal 成功。80 个执行源前后不变、10 个 native 工件复核，八份上游 raw 与上一批一致。
- 完整32头/128维 chunk 实际读739,344,384 B、写30,146,560 B、24,046,593 transport ticks，精确匹配公式；输出/state/scratch/history 均未发布。
- 同输入官方 suffix：BF16输出65,536元素，7处bit差、max2ULP、maxabs9.5367431640625e-7。完整FP32 state524,288元素，283,140处bit差、maxabs1.9073486328125e-6。
- state最大608,708 ULP位于index176561：actual=-2.359229256398976e-9，reference=-2.494389583773682e-9，abs差1.3516032737470596e-10。绝对误差与ULP都保留，不能只选好看的指标。
- Vector实际10,469,376次16lane Mul→Add调用，167,510,016 lane乘加对；算法有效27,754,496，定义排除补零token/causal上三角/ut未使用对角，主口径保留cold工作。Matrix前缀执行2,164,260,864 FMA、有效270,532,608 MAC，分开统计。
- 以上是实际软件执行及同输入诊断，未批准新的standalone误差阈值。M128也已沿同冻结源码完成，见下节。

## M128 已完成的实际证据

- 同一冻结80源/10native，八个实际终态全部成功，64个head×chunk完成；不是128次M1循环。
- BF16输出524,288元素，73处bit差，max48ULP、maxabs3.814697265625e-6、mean2.0491499556213322e-11；FP32 state524,288元素，334,393处bit差，max262,144ULP、maxabs4.76837158203125e-6、mean2.4004290849011264e-9，均finite。
- 实际读1,483,079,680 B、写56,885,248 B、888,832次写ACK、48,123,905 transport ticks与预测完全吻合。
- Vector实际20,938,752次16lane Mul→Add，335,020,032 lane对；算法有效284,950,528。Matrix前缀执行与有效均2,164,260,864。
- 主useful定义不按实际数值零做稀疏扣减。cold首chunk的已知零state predict/inter，以及其不再被消费的solve_k可另作理想裁剪分析，但当前没有省掉这些执行，不当成吞吐提升。
- 两档结果均经独立原raw/source/参考及计数复核；同输入诊断无新增PASS阈值。

## 复现与错误边界

- scripts/run_qwen35_35b_chunk_diagnostic.sh 接收 M、独立QKV全N8192报告/哈希、分别A/B原N32报告/哈希、全新输出目录。使用已提交payload下载/转换与runtime重建脚本准备同pin数据，禁止把参考raw导入为producer。
- 每次从实际RMS重新执行全部前缀。保存prep、chunk output、完整2MiB state及全部DDR scratch原始bytes到ignored work。
- 运行前小测12项；固定官方runtime smoke3项，覆盖M1/63/64/65/127/128、全局setter禁用、源/runtime漂移。M1 singleton非unit尾stride在原raw提取view暴露错误，现先无算术flatten再byte view；两档真实参考仍匹配原独立raw。
- 中断快照修正了读请求data=None、执行alarm与取证竞争；当前真实pending读/写均保留地址/tag/覆盖，取证前取消仅执行用alarm。成功或Numerical终态都保存scratch。
- 最终冷门、计划测试及发布CI见机器摘要和block_checklist；不得把smoke/源码检查称实际完整block验收。
