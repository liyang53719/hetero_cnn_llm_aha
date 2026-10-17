# 固定资源完整 block 必要预算检查器

日期：2026-10-17。只读源码审计与冷metadata代码片。未修改冻结源，未运行浮点数值、编译器、RTL、EDA或推送。该目录不处于Git checkout，因此未创建提交；可整体移入审核分支。source pins逐字节SHA256见SOURCE_PINS.json；不是将冻结组合冒充当前main。

## 用法与边界

`python -B budget.py` 输出预算JSON（源码未校验明确为null）；用README_PORTABLE.md的三个显式consumer-local source root参数验证18份源文件后再输出。`python -B -m unittest -v`、`python -B -O -m unittest -v`只跑计数测试。

固定useful=6,014,828,544、4096 MAC/cycle、ideal=1,468,464。80%最大整数cycle=1,835,580；90%精确预算4,894,880/3，最大整数cycle=1,631,626。正式测量必须从完整block launch到最终completion ACK，包含DMA/stalls。脚本只给必要下界或条件上界，永不颁发80/90 PASS；validate_claim显式拒绝将服务槽、理想供数升级为实测。

## 三种算法绝不混用

P=12×Σ(1..128)=99,072，R=12×128=1,536。

| 配置 | QK issues | PV issues | normalization调用 |
|---|---:|---:|---:|
| raw_scalar，原QK/PV | 792,576 | 792,576 | 792,576 |
| qk16_only，QK16但无packedPV | 55,296 | 792,576 | 792,576 |
| packed_qk_pv，候选算法 | 55,296 | 16,512 | 99,072 |

所有配置有16P次ordered fold Add，scale/subtract/ordered sum各P、Exp P、reciprocal R。raw与QK16-only primitive共27P；packed共20P。Dense统一最少1,462,272 issue。

真实compiled QK16的Qwen2Block.scala:102只有一个BlockScalarFloat；:296 calc寄存请求；:328–329严格request/result/resume；:544–545逐score 16 Add再scale；:558–562 softmax；:565–573按8个col块重复normalize。SHA256=4375ccf715cf408975c3e45ae595955767b824404ef8337bb260ed807527dc1e。此真实Chisel没有packedPV，不能代用71,808 attention issues。

packed算法现在绑定evidence_sources/packed_m128_schedule.py.txt的真实最终组合源码:32–74。独立review发现原M1/M2 schedule不能直接接tiled.patch；已调用原attention_packed_m128.prepare.compose完成包含M16中间片的零fuzz source-only组合，最终SHA256=a65dca9d24862c2b552117ce2c9cfdb270215b12881490fc50b5545b938b6086，与原generated pin一致。完整输入清单及组合收据在evidence_sources/PACKED_COMPOSITION_RECEIPT.json；可用recompose_schedule.py从显式消费者repo root冷重建。没有import或执行最终schedule，也不继承其数值PASS。其o._op/exp_negative是同步软件callback，不能将其Python时间或一次调用算一个硬件cycle。

## Scalar服务语义与端点修正

冻结BlockFloat.scala:39–55、71–98、108：Add/Mul accept→next accept最短3，cutoffExp3，fullExp20；options0正常Div是divider25/26加wrapper3，故28/29。Qwen2Block calc/resume额外空拍未计。

有限成功softmax每row至少一个exp(0)，故full_exp≥R，Exp服务槽≥3P+17R。所有Add/Mul按3、Div按28取最低。最后result ACK比下一次可接受早一拍，所以**service lower bound = interacceptance slot sum − 1**。此前口头报告用slot sum近似完成边界，多算1；此片已显式修正，结论不变。

优先排除依据是单Scalar服务界本身：raw/QK16-only为8,391,167，packed为6,310,655，全部已超过80/90总预算，不需要依赖任何跨阶段相加。packed槽总和6,310,656，端点修正6,310,655；保留Scalar与Matrix/Dense串行phase时，总wall下界7,844,735，对应useful利用率上界约18.72%。不含FFN SiLU、DMA、bank、max/BF16/controller及finalACK。该下界仅适用于声明的原单Scalar映射与无重叠条件；不限制未来有序borrower架构。

fullExp=P是显式条件：packed slot sum7,968,768，不能将此全full值当普遍下界。脚本要求full_exp范围R..P，不能凭猜测输入分支。

## SFU与阶段屏障

原SiLU16 vectors=71,680。options0除法本体至少25×71,680=1,792,000；options16候选14×71,680=1,003,520，只是候选服务界，非商位等价或STA。

保留完整前置阶段屏障：QKV/O Dense172,032 + packed Attention71,808=243,840；保留整个Act完成后才Down：Down430,080。于是options0与前后屏障下界2,465,920，约59.55%上界。这里容许Gate/Up完全藏在SFU背后，实际只会更差。

full-exp **vector** 指至少一个lane走full且仍遵守全lane屏障，不是full lane总数。若显式给71,680个full vector、保留当前微序列floor占用状态，则22×71,680=1,576,960非division状态槽，前+SFU+后下界2,250,880，约65.24%上界。22是21个ALU服务状态+1个转换状态；不能把22全称ALU节点，也不能对未来允许floor与另一context ALU重叠的调度无条件沿用该界。5是cutoff非division状态槽。检查器不给未提供分支数的运行自动添加全full界。

## 未接线与最小改动次序

1. 有序vector borrower：现Qwen2Block.scala:133–135有16个HeteroFP32Alu但无通用borrow mux；Scalar/SFU两池真实异常flags/owner/tag/active mask要接通。fold lane映射不同score，每输出16次Add顺序不变；禁止树归约。
2. SiLU微序列：VectorSilu.scala:29–84仍六phase issue/waitAll；保留phase4/5 BF16，先单context、options0做小片。sfu_silu_cycle_candidate/model.py:226–244的商仍callback，只有counter逐边沿。
3. options16独立开关：仍16 divider但增加trial/subtract/select，须另做数值与STA，不能称同面积。
4. 有界context与loan预取：预留不可反压divider返回及held store结果；不能借用已有寄存器名称而忽略存活冲突。
5. bank/FFN阶段流水：FfnResidentCoordinator.scala:31、90–110严格Gate→Up→SiLU→Act drain；FfnTileSiluBridge.scala:37–47、68–72单vector串行；TransposedDenseOwner.scala:824–832窗口active排斥external tile；TransposedDenseBanks.scala:148–175、211–229只有3槽、单outstanding、整tile seal/release，:249–288共用bank口且write为RMW。删除互斥guard不是合法overlap。
6. 要消除前/后屏障需独立token/Down流水提案，不与本计数片混写。

当前scratch仅当前query/KV的6个head row，因此softmax按同key跨head组包最多6 active lanes，Exp包16,512、reciprocal包256。把P直接除16是假定了未证明的跨query缓存。可比较16-key exp后原序sum方案，但必须计结果寄存器、panel生命周期与bank服务。

## 下一片真正联合event模型的接口

不在本片实现；应逐一接下列原接口，而不是替换为feed_ready=True：

- MatrixPipelineService group/request/result/done、context/last与held result credit。QK结果保持到score bank ACK，PV保持到最终输出ACK，禁止提前ACK后复制完整host tile。
- FfnWindowPort request/result/leaseValid/invalidateLease，含ng/slot/rows/cols/identity。
- FfnTilePort control/read/write/response、sealed/produced/consumed、drained、leased及对应16个A bank读/RMW写预约；从已接受事务推导次拍端口占用。
- FfnSiluLoanPort request/result/busy/drained/abort；扩展通用opcode需与原SiLU互斥。16 divider outValid pulse必须预先预留返回寄存器与tag。
- FfnDrainPort request/result及DDR最终write response；burst request/response和writeRequest/writeData/writeResponse分别保留债务。
- HostBlockCommands job/result、resident group及handoff/flush，保留最终Host completion条件。
- 现96-word panel、Q128-word、V/Matrix256-word packet逐一映射物理寄存器/银行，列活跃区间，不增完整tensor cache。

事件模型实验应逐配置比较raw、QK16-only、packed、borrower、microsequence、options16、context、bank overlap，不改变数值合约；真实分支统计后给条件预算。直到真实完整RTL launch→finalACK计数、数值门、资源/STA均验收前，80/90保持未验收。

## 独立review修订

已补最终组合schedule与原链source-only重建入口；Dense常数改为M/H/F/KV维度公式；用控制状态标签序列冷复核Add3/fullExp20/Div28–29与末ACK−1；新增threshold两侧、分支类型/范围、篡改pin负例。SiLU界明确要求完整成功、每vector执行normal有限非零分母除法。
