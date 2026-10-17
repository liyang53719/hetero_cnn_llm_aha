# v2 残余路径与public限制：只读后续方案

原v2 FAIL保持；不新增waiver、不执行工具。

## FIFO ready_o 位依赖

原 cc_passthrough_stream_fifo.sv:64–108：flush时 ready=0；其余情况下
ready_o = ((R.phase==W.phase) ? 1 : R.index!=W.index) || (SameCycleRW && ready_i && valid_o)。

valid_o已证只Q/flush。ready_o没有valid_i依赖；valid_i只写data_d/write_ptr_d。同always把 valid_i/in_valid → ready_o 合并，形成 read.in_ready → read.in_valid → FIFO ALWAYS → ready_o → read.in_ready 的假边。精确 isolate_assignments -module cc_passthrough_stream_fifo -var ready_o 有直接源码依据。添加这一条时仍保留valid_o隔离，不能以删除readvalid握手或改FIFO策略解决。

## 顶层public split拒绝的官方源码依据

官方 `verilator/verilator@v5.032/src/V3SplitVar.cpp` Git blob 26b2cd20817d0f87ebf43c7b1f4de815e108abbb（本地快照 V3SplitVar_v5.032.cpp）：182行 cannotSplitVarCommonReason 的 isSigPublic 返回 “it is public”，与实际v2 SPLITVAR完全一致，不再向顶层axi_write_req_o申请拆分。

该文件1166–1170行对成功拆分的IO保留原port并 connectPortAndVar，IO本身不是全部禁止；方向ref/inout另有约束。官方 `src/Verilator.cpp` 253行执行splitVariable，298行才inlineAll。故**非public子模块输出**在inline前拆分有官方源码路径支持，并非改top public属性或隐去告警。

## 最小下一候选（尚未创建运行）

保留v2的4个isolate(valid_o/first_w/last_w/aw_sent)，添加fifo.ready_o，撤掉失败的top split，改为精确 `split_var -module "idma_axi_write" -var "write_req_o"`。该变量原声明在idma_axi_write.sv:67，类型write_req_t，经原wrapper实例化为packed AXI request。模块不是独立top，source中无public标记；不增加--public类flags，不改ABI，不改冻结源。

该内部变量在:131/132分别写AW字段，:185写W.valid、:193–205写W.data/strb；:270从其W.valid导出w_chan_valid_o进入coupler。拆分目标正对真实AW/W聚合假边。即便先于inline存在合法拆分路径，后续优化/别名可能重合并，因此不能保证一次成功。运行时SPLITVAR或残余UNOPTFLAT仍fatal，若内部也被判public/不能拆，立即保持FAIL并调查，不换另一个未经审定变量碰运气。

所有声明匹配/原pins/293subset/21width/预算仍需后继独审。这里只提供来源和等式，不代替下一runner或root执行授权。
