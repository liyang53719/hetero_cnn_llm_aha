# 四 UNOPTFLAT 位依赖诊断（原 FAIL 保留，未重跑）

## 判断

本轮原日志所列四条**示例路径各含可明确定位的非真实信号依赖边**：同一always块内next-state计算与独立控制输出混算，以及 packed AXI request 内AW/W字段合并。按下面原源码等式切开后，本wrapper边界的这四条路径没有位级组合回路。尚不能把手工路径分析称整个RTL无环证明；工具v1仍FAIL，必须新的限定配置资格才可确认。

与真正同一位自反馈的SFU组合环应区别：这里切断的是图中不存在的控制依赖，既不插寄存器，也不靠初始值或二态settle收敛。没有将UNOPTFLAT设置为非fatal。外部AXI响应输入视为独立边界，未证明任意上层互连和从设备组合连接都无环。

## 1. fifo valid_o / read in_valid 路径

cc_passthrough_stream_fifo.sv:64–108同always块包含valid_o、ready_o、next pointers和写数据。固定Depth3，令R/W为注册指针、F=flush：

valid_o = !F && ((R.phase==W.phase) ? (R.index!=W.index) : 1)

因此valid_o仅依赖注册R/W和flush，不依赖本周期valid_i/ready_i。ready_o在非flush时等于not_full || (SameCycleRW && ready_i && valid_o)，而指针/data_d才依赖valid_i。日志的read.sv:168 in_valid → FIFO ALWAYS → valid_o边是同block过近似，不是真值依赖。

真实顺序：注册FIFO状态→buffer_out_valid→first_possible/first_w/last_w→mask_out→ready_to_write→write_happening→buffer_out_ready→FIFO ready_o→read in_ready→in_valid→FIFO next_state；最后一段只到D，必须时钟才能回到Q。

## 2. write_happening → first_w 路径

idma_axi_write.sv:224–268里同时计算first/last与计数器D：

first_w = is_single ? 1 : (first_possible && !w_cnt_valid_q)
last_w = is_single ? 1 : (w_cnt_valid_q && w_num_beats_q==1)
first_possible = all(buffer_out_valid & w_first_mask) && any(buffer_out_valid)

write_happening仅在后面的if里改变w_num_beats_d/w_cnt_valid_d，不能反过来改变first_w或last_w。日志 write_happening→ALWAYS→first_w是假的block边。真正mask_out依赖上述first/last、offset/tailer、mask_ext；ready_to_write依赖dp_valid和buffer valid/mask；write_happening再与外部w_ready相与。到next-state后跨时钟，没有同一位反向边。

## 3. aw_sent / fallthrough fifo_empty 路径

idma_channel_coupler.sv:132–162有输出aw_sent和credit计数D：

first = w_req_valid_i && w_req_first_i && !aw_stall_q && !w_decouple_aw_i
aw_sent = aw_valid && (aw_decoupled_head || first || aw_to_send_q!=0)

aw_ready_decoupled只参与credit_D的加减，不参与aw_sent等式。fallthrough寄存器Depth1：full=(status_q==1)，push=aw_sent&&!full，empty=(status_q==0)&&!push，aw_valid_o=!empty，ready_o=!full。返回aw_ready_decoupled仅是注册full的函数，因此没有empty→ready→aw_sent的真实反馈。

## 4. packed axi_write_req_o 的AW/W假合并

所有四条日志的后半段都把整个axi_write_req_o作为节点。源idma_axi_write.sv:184将ready_to_write送 **w_valid**，191块仅写 **w.data/w.strb**，217写 **w.last**；generated:8961–8970 coupler输入w_req_valid_i来自w_chan_valid（write模块的w_valid），first来自first_w，coupler输出只接 **aw_valid_dp→AXI aw_valid**。

因此真实依赖是 W.valid/first→coupler.aw_sent→AW.valid，并无 AW.valid→W.valid。日志把AW.valid变动当成整个struct变动，再把W.valid当作回边，才闭合示例环。packed struct位字段必须分开分析，不靠grep出现同一变量名认定真实环。

## 可审定最小修复候选

不修改冻结provider，优先外部 .vlt 配置：
- isolate_assignments 精确 cc_passthrough_stream_fifo.valid_o
- isolate_assignments 精确 idma_axi_write.first_w / last_w
- isolate_assignments 精确 idma_channel_coupler.aw_sent
- split_var 精确 idma_backend_rw_axi_flat_wrap.axi_write_req_o

完整候选 structural_hints.vlt，仅这5项，不含lint_off UNOPTFLAT、通配module/var或-Wno-fatal。保留先前21 WIDTH限定规则、293源和所有pins/params。官方5.032 extensions.html:421说明isolate_assignments拆独立输出赋值，:678说明split_var可处理packed struct integer fields；exe_verilator.html:2877/3019给对应精确module/var配置形式。文档hash记录在SOURCE_PINS.json。

这是**新的工具结构提示资格候选**，不是执行成功或语言语义修改证明。配置可能不作用于alias/port或产生SPLITVAR告警；若有任何新warning，仍fatal，停止诊断，不增白名单。若该精确配置不足，后续备选是独立overlay source把上面独立输出赋值拆成连续assign，保留原provider，先给逐文件diff/等式等价审查再获准运行；不能现场改上游凑PASS。

如需更多图证据，可单独申请固定--report-unoptflat诊断（仍需新预算/授权），不要暗加工具执行。本轮没有运行Verilator、仿真或生成器。
