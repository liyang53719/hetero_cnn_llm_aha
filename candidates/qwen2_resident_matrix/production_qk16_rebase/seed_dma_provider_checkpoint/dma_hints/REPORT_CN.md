# fullBench DMA read高层路径：位级诊断与工具配置候选

原noinline fullBench超时保持FAIL。当前显示路径不是此前孤立wrapper资格覆盖的高层环境；本结论重新读取真实generated adapter和固定iDMA源码，不沿用孤立PASS推断。

## 精确两处假边

实际类为 RetainedIdmaWeightBurstAdapter（IdmaWeightBurst.scala:31），不是另一个BurstMemoryAXIAdapter模块。generated collection模块起498965行，source/hash见SOURCE_PINS.json。

1. idma_axi_read.sv:108 read_req_o.ar_valid=ar_valid_i；:164 read_req_o.r_ready=in_ready&r_dp_ready_i。generated collection:499293取rr_r_ready=_rr_WIRE[0]、499295取rr_ar_valid=_rr_WIRE[1]。in_ready只改变R.ready bit0，不能通过同packed read_req_o改变AR.valid bit1。日志从in_ready→read_req_o整体→AR.valid是非真实位依赖。
2. IdmaWeightBurst.scala:293–297（generated499961–499987）：
   ARfire=ARvalid&&ARready；rid=ARfire?ARid:extId_q；last=(externalCount_q+1==count_q)；bad=(RID!=rid)||(RLAST!=last)||(!arSeen_q&&!ARfire)。
   rs.r.resp=bad?DECERR:external_RRESP；rs.r.last=last，rs.r_valid=external_RVALID&&!externalDone_q，R.ready=backend.R.ready&&!externalDone_q。
   bad不门控R.valid、R.ready或r.last，只选择r.resp（以及R握手后的fault寄存器）。generated499985独立驱动rs_r_last，499986驱动resp；打包532bit response时r.last位1、r.resp位3:2，明确不同位。
   iDMA read.sv:116–126的mask只读first_r_q、offset/tailer和read_rsp_i.r.last，不读r.resp。bad→packed response整体→mask中的last是第二个假边。

真实read mask等式：M = (first_r_q?first_mask:all_ones) & ((tailer!=0 && r.last)?last_mask:all_ones)，mask_in为M按shift旋转；in_ready=AND(buffer_in_ready | ~mask_in)。此链没有RRESP或bad的反馈。外部响应及注册状态固定时，改变in_ready不会改变AR.valid；改变bad只改resp不改mask，故所显示循环没有该路径的无固定点反例。

只证明显示的这条路径在字段级断开，不证明整个Host所有组合路径或任意外部AXI从设备无环。r.resp另有错误响应传播路径，不在本显示mask边中，后续实际全top仍需独立资格。

## 协议必须保持

rid在同拍AR.fire选择新ARid，允许同拍AR/R零延迟响应；bad对未接收AR却来R、错误RID/RLAST做组合DECERR，握手后再粘fault。不应删除bad、不应把bad寄存一拍、不应让bad门控R.ready/R.valid，更不能用外部valid假设抹掉早fault。此次仅工具内部字段拆分，没有source/端口变化。

## 最小工具候选

在已审6条wrapper hints后追加且仅追加：
- split_var -module idma_axi_read -var read_req_o
- split_var -module idma_axi_read -var read_rsp_i

声明分别位于固定idma_axi_read.sv:60/62，read_req_t/read_rsp_t均由原rw_axi实例化为packed AXI structs。模块是fullBench内dma.backend.u_backend.i_idma_transport_layer.i_idma_axi_read，不是public顶层；原source无public标记，原argv没有--public类开关。官方v5.032 V3SplitVar.cpp:182仅拒isSigPublic、1166支持保留可拆IO，Verilator.cpp:253先split、298后inline（来源见复用OFFICIAL_EVIDENCE.json）。这支持内部input/output候选，不保证后续alias不重合并。

validate.py对完整8条配置精确顺序/无额外规则、8个唯一module/var声明和固定源SHA进行fail-closed检查；源码匹配不等工具内部hit遥测。SPLITVAR、残余UNOPTFLAT或任何新warning仍fatal。没有增加waiver、没有禁用bad，没有修改冻结provider，没有执行工具。fullblock agent应将这两个目标纳入自己的完整source/runner/hash与实际context验证，seedpatch仍是独立问题。
