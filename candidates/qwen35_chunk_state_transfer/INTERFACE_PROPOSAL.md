# 独立私有状态搬运 owner，接口与有限范围提案

不改原公共/Host/recurrent/M1 fence，不接 Host，不实例化额外 Matrix、Vector、Scalar、DMA 或 SRAM。新增一个真实 Chisel Module 与本批独立 job/result/port 类型；仅单个 512-bit 搬运寄存器、当前 job、地址/事务计数与 FSM。编译、elaboration、RTL/真实仿真均未执行也未准入。

## 固定内部命令

GdnChunkStateTransferJob：context=原 GdnChunkJob，head=UInt16（拒>=16），operation=UInt2（0 Initialize、1 ExportFinal，其余拒）；另携带两份原 GdnChunkStageReceipt（nextStateReady/outputReady，仅 ExportFinal 消费）。不是公共命令编码，也不新增可用的 Vector 端口。

Port：job Flipped Decoupled；committed Input 原 GdnChunkCommittedState；memory Decoupled 原 MemoryRequest；response Flipped Decoupled 原 MemoryResponse；done Decoupled 新私有结果；resetRequired Output。

每次命令处理一个 head 的 65536 B（1024 拍），不遍历算术阶段：
- Initialize cold：写零到该 head 的 initial；不读取 stateIn。
- Initialize warm：stateIn + head*65536 →该 head initial，逐拍 read response 成功后才 write。
- ExportFinal：该 head 末 chunk 的 next_state → stateOut + head*65536。没有中间 chunk 的 stateOut 提交或 root 更新。

原 AddressPlan 固定存储：headStride 为 M16 872448/M128 1679360；initial=head scratch 起点；末 next_state 相对 head 为 M16 806912/M128 1613824；每拍偏移 beat*64。常量从原 Geometry/AddressPlan 元数据推导并以已验证值作 require，不改布局。

## Admission 与依赖

仅 tokens16/128，heads固定16、FP32 state；expectedGeneration<0xffffffff且等 committed.generation。cold要求gen0且committed.valid=false；warm要求gen>0且valid、committed.state==context.stateIn。维持原五完整 span 的64B对齐、宽位 end<=2^56、十对不重叠；地址先宽位计算再赋64bit。

ExportFinal 额外逐字段验证两份私有依赖 receipt：同 tag/gen/head/末chunk、status Ok、drained。
- nextStateReady：phase16 StateAdd；scratchAckBytes65536，output/stateAckBytes0。
- outputReady：phase17 OutputMaterialize；outputAckBytes=M16每head4096、M128末chunk每head16384，scratch/stateAckBytes0。

这只是未来可信内部 chunk scheduler 的绑定输入检查，不能证明 receipt 真实来源；本批没有生产算术/receipt producer，也没有 Host 接线，因此不得提升为完整 chunk或可对外发布的控制入口。未来集成必须将 receipts 来自真实接受/匹配响应的 owner，而不是任意软件许可位。Initialize 不消费这些 receipts。

## 原 Memory ABI 与完整拍边界

现 Protocol.scala 的 MemoryRequest 固定512-bit data、64-bit mask/address/tag；MemoryResponse 只有 data/tag/error，根本没有 nbytes。本批不扩这个共享 ABI、不伪造 nbytes 检查。只发对齐64B固定完整拍：写mask全64位1，读mask0。需以既有完整拍 transport 错误传播为集成前提；本owner只检查其真实可见 tag/error。未来若要独立短响应计数，须另审接口，不能从 data512 宣称已检测实际 nbytes。BlockAxi固定LEN0/SIZE6且检查ID/RESP/LAST；RetainedIdma依赖原backend执行64B length，检查mailbox完整拍并等local/external/iDMA三个完成条件，但不是可见nbytes证明；SharedMemoryArbiter会把下游tag失配转为原client tag加error。

## FSM 与 ACK 规则

idle → issueRead/waitRead → issueWrite/waitWrite → … → finish；cold直接issueWrite。只有memory.fire才置单 outstanding；等待响应时不发新请求。稳定寄存器保证请求backpressure下地址/data/mask/tag不变；tag=Cat(context.tag,sequence)。

仅匹配tag且error=false的response.fire允许sequence递增；读成功只记readBytes并锁存512-bit数据；写成功才writeBytes+=64且推进beat。最后一拍写ACK之前不transferComplete。错误tag不清待结债、drained=false；匹配error响应即使清本地bookkeeping也必须status失败/resetRequired且localDrained=false，因为arbiter可能将下游tag失配折成同tag的error响应。任何失败不计该失败拍字节，terminal held，消费失败terminal后进入locked直到reset。成功terminal消费后回idle。

结果只含 tag/gen/head/operation/status/readBytes/writeBytes/cycles/transferComplete/localDrained；没有stateCommitted/historyCommitted/generationAdvanced/新根。localDrained仅在status Ok且本owner无outstanding时为true；任何失败保守false，无权声称共享fabric/算术/整job无债。held done 在backpressure下全部稳定。成功复制不改变任意FP32 word，包括NaN/符号位；这是bitwise搬运，不做数值筛选或运算。

失败可能留下部分私有写入，本单元不回滚；这些字节不得被发布。失败 terminal 消费后的 locked 必须连同原共享 transport 排空或复位后才可恢复，不能仅复位 owner 将旧响应算进新命令。成功再入的相同 tag/重新归零 sequence 依赖既有 fabric 每请求唯一响应且没有跨命令遗留，不声称防重放。等待 done.fire 时所有结果字段（包括 cycles）冻结，job.ready/memory.valid 均 false。committed 与 receipts 只在 job.fire 检查；可信 scheduler 必须保持整 job 期间来源矩阵和根稳定，本单元没有原子全局锁或 receipt 来源证明。

## 对应小测试范围

新纯stdlib状态机模型＋source/固定接口 pins：M16/M128、head0/15、三路径每拍地址/data、cold零读、warm读后写、末拍ACK门、request/done backpressure、错tag/响应error/失败计数、先后次序、generation/span/alias/依赖receipt拒绝、terminal后锁定与成功再入。模型接受显式事件，不冒充 Chisel 执行或真实AXI握手。地址与原已验证Scala AddressPlan literal/已封行为结果交叉；不运行RTL、不执行昂贵模型，待源码冻结后另交root有限小测试准入。
