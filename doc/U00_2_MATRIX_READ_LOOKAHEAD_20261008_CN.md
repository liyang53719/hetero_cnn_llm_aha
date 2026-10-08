# U00.2：默认关闭的单请求 Matrix read lookahead

## 范围与结论

基线为 `cc572c39fbe514cd7ff9f97fbc0a8bd5a9b5e6ab`。在既有
`qwen2_shared_l2_matrix_tile16_payload` 增加默认关闭的
`CANDIDATE_READ_LOOKAHEAD`，只提前提出下一 K 的 activation 请求。
默认路径保持原逐周期行为；顺序 K、FP32 FMA、BF16-RNE、异常与提交协议不变。

本地终态为 `PASS_SINGLE_OWNER_MATRIX_READ_LOOKAHEAD_AB`。8个冻结主A/B、
最后random/all及末端source/fixture/manifest封存全部通过。
两来源分别独立验证，所得周期一致：

| fabric条件 | default周期 | lookahead周期 | 节省周期 | 周期下降 | 固定512-lane候选command-wall |
|---|---:|---:|---:|---:|---:|
| 无人工请求/响应/DMA/ACK延迟 | 2,100,332 | 2,100,332 | 0 | 0% | 14.0412087% → 14.0412087% |
| transaction-indexed确定性延迟 | 5,194,998 | 4,900,382 | 294,616 | 5.6711475% | 5.6768453% → 6.0181431% |

延迟条件下为约 `1.060121×`，仅适用于所测fabric条件。
无停顿回放没有周期提升。不能把global-cycle LFSR同seed称为相同延迟序列，
因此保留的random stress只作健壮性验证，不用它与旧版本作因果加速比较。

以上是该候选命令的接受到done周期，包含DMA、ACK及串行Norm/RoPE；
不是完整block、宏SRAM/DDR物理带宽或PPA结果。gamma/trig仍由测试前置准备，
系数生成/cache及完整Command128接入尚未完成。

## 实现与不变式

- MQ(K) 且非末K时可提出 A(K+1)。只增加一个pending控制位，没有新增数据buffer、outstanding计数器、SRAM或算术lane。
- 当前 A/W/K/clear/last 保持到实际Matrix input fire。早到响应在既有L2 owner处保持，不能提前覆盖A寄存器。
- Matrix fire时，若请求已接受或同周期接受，转ARP；否则转ARQ。同一被背压的地址跨MQ→ARQ不变，不重发、不丢请求。
- 末K不预取，不跨tile。输出写入和done前必须无未完成read；reset同时flush fabric和owner。
- 参数经既有candidate controller传递，legacy分支没有启用新参数。所有参数默认0，并追加在原参数后以保持位置参数兼容。

新instrumentation记录真实input fire时间、A/B/K/context/clear/last、
valid&&!ready、四个operand等待状态、read owner占用和response hold、
请求到响应延迟，以及context/FIFO/array admission的互斥stall分类。
计数来自真实端点和scheduler，不能把重叠观察值相加充当周期分母。

## 因果A/B与周期解释

确定性replay以每命令、每channel的请求序号和固定salt生成admission、
response及同周期ACK预算；不依赖全局cycle或LFSR。独立Python消费者重新计算
每个channel的预算和64位fingerprint，再逐命令核对两模式相同。
无停顿条件去掉人工delay，但仍经过实际behavioral `shared_l2_fabric`。

独立状态计数闭合说明：

- 无停顿：ARQ减少294,624周期，context stall恰增加294,624，墙钟不变
- replay：ARQ减少294,874，ARP减少54，context stall增加312；净值恰为294,616
- 不变的context0 recurrence要求input II≥5，因此当前单context理想上限为20%，全命令更低
- 每步仍需A64B加W64B，单beat payload读口的供数理想上限为50%；小预取不能独立达到90%

没有为增加utilization而旋转同一K归约的context、改变累加次序，或缩小分母。

## 冻结数值与协议门禁

每来源仍为cold token0..15、carried112..127的全部Q8/K2：32选定token、
320 head-token、288 tiles、294,912实际Matrix输入与输出包，
150,994,944个有效逐K累加器观察值。两来源、两fabric、两模式共8次完整回放。
这是重复对照同一冻结工作量，不能把重复回放计成更多唯一token覆盖。

- 输入只来自原始H1024 BF16 activation和固定checkpoint权重；没有注入native projection
- 每个input的全部operand及metadata核对；每个output的全部512 lane逐位核对独立整数及C参考
- 原native `max_abs≤0.03125`、`mean_abs≤0.005`不变；selected gate通过不替代仍为false的完整native block gate
- main stream保持严格单read owner、A/W/K顺序、全写ACK、head/token提交边界及input II≥5
- 新primary verifier显式要求input事件；旧output-only历史trace仅保留明确的兼容模式

小K门禁两模式各50例：K=1/2/5/31、tail掩码、请求先于/同时/晚于Matrix接受、
early response、late Matrix、非法形状和非有限值、5个reset/recovery点。
旧HEAD payload与默认关闭新payload在该范围所有输出逐周期相同。

额外actual-wrapper门禁在真实Matrix/SharedL2上命中A2早到响应：

- 请求在Matrix1被阻塞时接受，响应在旧operand释放前保持
- L2错误随后握手，status8、无写入、无残留read；2输入/1输出，明确flush一个在途Matrix操作
- reset在held response时发生：1输入/0输出，明确丢弃一个pending read，并检查无晚到完成
- 两次恢复各完成16,384真实K输入/输出，合计32,769已发出Matrix512输出全部独立核对

这两个abort有合法的输入/输出差异，使用单独的严格消费者记录；没有放松主门禁。

## 回归、证据与重建

- 相关normal及Python -O各1,372项通过，无排除，包含三项C/compiler测试及两个实际payload RTL bench
- 最终全仓4,042通过，仍是同5项既有失败；不是全仓全绿
- 旧发布终态基线为3,888通过；早期机器日志3,857尚未包含后加的31项phase测试
- 未执行综合、时序、PPA或real macro-fabric带宽验收

结果文件保存在 `reports/execution/U00_2_MATRIX_READ_LOOKAHEAD_20261008/`。
random/all共49事务：10成功、35准入拒绝、2故障、2reset；450,560个实际Matrix输入及输出、
12,800次明确写ACK全部核对，tail17完成第二批单行尾部。

主stream逐条完整进入独立消费者直到EOF，保留原始流SHA、字节/事件数、input/owner统计和结果，
不保留主回放原始流；再次逐事件审阅需要重新生成。小型held-response完整压缩trace保留在本地。
独立评审明确区分重新扫描的补充trace与只核对receipt/计数的主stream，不冒称后者已再次扫描。

标准主门禁：

`python scripts/run_matrix_read_lookahead.py --output work/NEW --jobs 2`

公开CLI默认从pinned官方payload重新生成两套来源和整数/C参考。低磁盘本地模式可用
`--cached-vectors work/matrix_tile16_final/vectors`，只接受已发布的固定receipt，并前后重核
官方provenance、源码、全部向量文件和权重hardlink；没有任意saved-array digest CLI。

补充门禁：

`python scripts/run_matrix_read_lookahead_edges.py --cached-vectors work/matrix_tile16_final/vectors --output work/NEW_EDGES`

CI在同一进程中接续主门禁刚生成的fixture/receipt执行补充门禁，另独立绑定644个
primary/supplemental案例的原始输入和参考文件hash。Git及CI artifact只保存源码、pins、
哈希与短摘要；checkpoint、NPZ、memh、逐K二进制、生成RTL及可执行文件不进入Git。
只清理本任务已无使用者的可重建compiler生成物，保留日志及唯一最终证据；
正在回放的主tb二进制始终保留。

## Checklist与边界（本地封存快照）

- [x] 默认关闭单owner实现与小K协议门禁
- [x] 真实输入fire、latency/occupancy/context stall instrumentation
- [x] 两来源全部冻结主A/B、严格相同replay预算及完整数值核对
- [x] held-response read error/reset与完整恢复
- [x] 默认逐周期对照、normal/-O及全仓回归
- [x] 最后random/all与末端source/fixture/manifest封存
- 提交后另行验证source-only main推送、精确新HEAD全部CI及artifact摘要；本地PASS不代替远端终态

U00.2保持ongoing，U01保持to do。全M128实际RTL、完整Command128、系数cache、
KV/Attention/FFN、三模型完整block、PPA和固定资源整block MAC90%继续OPEN。
