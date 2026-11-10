# TEMP 局部 UInt cat/bits 候选，未接 Host

实际实现 `ExactUIntSlices.slice` 使用 FIRRTL2 Expression：精确消解 Cat 内部切片、跨界切片、嵌套 Bits、UInt 常量，并可沿调用方明确提供的 immutable UInt DefNode alias 消解。未知表达式完整保留（必要时外包Bits），不删 Mux 条件、不跨寄存器/端口/存储器、不猜 last-connect。

独立值解释器检查 1000 个随机/边界切片（1/2/4/64/512与1/3/8/532位组合），包含全宽、左右半、跨界、随机前缀；实际785/532位局部布局及alias/嵌套Bits通过。ar_valid切片输出恰为单个Reference(ar_valid)，r_last切片恰为Reference(r_last)，因此局部引用集合分别只有该字段，而非全部packed字段。没有修改 native r_ready→r_last 依赖。

`graph_check.py`读取并pin当前low.fir，仅确认真实wrapper请求Cat末端及r_last提取表达式，再对日志环的手工约化图作前后对照；**不是当前完整IR自动依赖图或实际环消除证明**。约化图after假定已把字段贯穿连接边界，这个条件当前尚未实现。

实际环仍跨 `dma.backend.axi_read_req_o`/`dma.backend.axi_read_rsp_i` 端口，以及父层连接、`_rr_WIRE`和节点。局部DefNode-only算法不足跨越这些边界，不能宣称Host环解除。若接入PrepareAst之后的flatten IR，仍必须审计每个alias是否唯一无条件驱动、位宽/符号类型一致、无寄存器/黑盒/多重connect语义，不可未经证明扩大last-connect替换。优先以明确wrapper字段贯通变换或受限且验证驱动关系的连接alias作为后续独立步骤。

编译首次因BigInt shift参数类型报错，修正 `.toInt` 后编译/测试exit0；不涉及算术或数据改变。未启动Host、未改变运行中classes、未AllowCycles、未clock hack。其他环、native执行、数值、利用率均无新通过结论。
