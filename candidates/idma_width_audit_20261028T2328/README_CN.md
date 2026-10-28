# iDMA 四处截断及缺失引脚只读审计

状态：**固定配置静态范围审计通过；不是完整 frontend / RTL / prefill 数值 PASS**。
未改任何源文件、参数、警告设置；保留 R3 失败日志。只新增本目录隔离审计脚本/JSON/说明。

## 实际实例与参数

`HostBlockTopV4.sv:1320673` 实例 `RetainedIdmaWeightBurstAdapter dma`；同文件 `1268335` 实例 `idma_backend_rw_axi_flat_wrap backend`。原 R3 警告确切实例是 `HostBlockTopV4.dma.backend.u_backend.gen_hw_legalizer.i_idma_legalizer`（page splitter 下接 i_write_page_splitter）。

`providers/idma_backend_rw_axi_flat_wrap.sv:61–68`：src/dst max_llen=4、reduce_len=1；DataWidth=512、AddrWidth=64、TFLenWidth=32、HardwareLegalizer=1、RejectZeroTransfers=1、EnableCompute=0。没有覆写 BurstLen；`idma_generated.sv:8283` 默认8。`8623–8653` gen_hw_legalizer 将参数透传至 legalizer（确切实例行8637）。

`idma_generated.sv:3974–3990`：StrbWidth=512/8=64，OffsetWidth=clog2(64)=6，PageSize=min(256*64,4096)=4096，PageAddrWidth=12，page_len_t=13bit，offset_t=6bit。

## 两处 page_addr_width 截断

`idma_legalizer_page_splitter.sv:28,34,38–40`，接收4bit、表达式32bit：
- 不突发分支是6。实际 read/write splitter not_bursting_i 都接0。
- 突发加数是3bit max_llen 的0..7或默认BurstLen=8，因此截断前6..14，均小于16，不丢有效位；之后clamp12。
- 实际有效事务 max_llen4/reduce1，故page_addr_width=10、page_size=1024。
- 结论只覆盖此固定参数。不能推出所有参数安全，例如OffsetWidth8 + BurstLen8 =16会在clamp之前截为0，这是泛化配置的潜在缺陷，当前512bit实例不触发。

## 两处 AXI len 截断

`idma_generated.sv:4241/4269`：8bit AXI len接收 `(num_bytes+addr_offset-1)>>6`。
令实际虚拟页低10位为a，低6位o=a mod64，剩余边界字节B=1024-a。splitter:45–60计算B；legalizer:4078–4147将num_bytes置为min(remaining_length,B)，耦合时也不会大于本侧B。

对于有效事务：1<=n<=1024-a，故0<=n+o-1<=1023-a+(a mod64)<=1023；AXI len属于0..15，8bit无信息丢失。更宽松地覆盖运行选项产生的全部k=6..12虚拟页，AXI len最多63，仍无截断损失。13bit n与6bit o在实际范围无加法溢出；计算上下文更宽不影响此结论。

正长度归纳：wrapper启用RejectZeroTransfers；backend:8560–8565将零长度的valid置0，:8616–8617在EnableCompute=0分支透传req_valid，:8641将其送legalizer。legalizer:4159–4178装入正长度；若remaining>B，则下次remaining=remaining-B仍正；否则本次终结并清valid。:4319–4326只在tf.valid时输出valid。compute长度缩减路径关闭。因此**有效突发**不会因n=0使减1下溢。空闲/reset状态原始组合len可能下溢，不能声称所有无效周期的len信号都0..15；其valid=0，不纳入事务安全结论。

`check_ranges.py` 用整数穷举每种k的所有a与1..2^k-a，不替代HDL仿真。实际k10共524800组max15；全部k6..12共11188192组，最大63。检查失败显式抛错，不依赖Python assert。

## 三处 PINMISSING 的范围

三条日志都是同一源码 `axi_stream_cut.sv:41` 中 cc_spill_register 缺 clr_i；不是三个不同活跃实例。`cc_spill_register.sv:23,37`确有同步清零输入并继续传入flushable，所以不能说此端口本身没用或已接0。

扫描523个恢复/生成SV、SVH：包括导出树、物理providers、192MB实际Host、实际FMA子集。四个名称 axi_stream_cut/cut_intf/multicut/multicut_intf 的所有出现只在定义它们的两个文件，见range_results.json完整行号清单。模块边是 cut_intf→cut、multicut→cut、multicut_intf→multicut；无来自此闭集之外的命名引用，因此**静态命名实例图中，此缺口不在Host可达闭包**，并非以告警文本无instance猜测。三个frontend阶段分别解析同一宽源列表，解释重复告警。

限制：此处不是完成Host elaboration之后的实际实例对象/网表证明，也不是通用SV token-paste/elaboration形式证明；R3因日志上限停止，Host产物尚缺。未来如启用stream-cut路径应显式处理clr_i，不能迁移本次不可达结论。当前不建议为了这个离线模块更改固定硬件或屏蔽警告。

## 证据

源文件SHA256见range_results.json；原wrapper a82bc50f…、page splitter d68f3926…、generated iDMA b6423c42…。R3frontend.log SHA256972eb92bfbbd5f705b2867e3e2460dbcb491ca0f0f89be10cdf6350102794373，仍保留；本审计不将33087条其他警告归为安全。
