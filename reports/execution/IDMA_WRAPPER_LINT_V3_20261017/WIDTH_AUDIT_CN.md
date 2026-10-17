# 固定原参数 iDMA：B2 warning 只读审计

## 结论

原 B2 失败为 bad_alloc，不能称完整 elaboration 通过。本次从原日志精确抽出 **23 WIDTH 警告（19 WIDTHEXPAND、4 WIDTHTRUNC）和 1 PINMISSING**，未运行工具或改变 provider。每条 rule、文件、行列、原实例路径和当前源 SHA256 完整列于 WARNINGS.json；实例均来自失败前真实工具记录，不能由此推断后续未完成部分。

固定 512-bit wrapper 下，四个截断点具有可证明的有效事务值域，不构成本配置中的丢位错误。其余19个为无符号扩展/零扩展，未发现因扩展本身改变值的错误。这个结论不覆盖随意修改 DataWidth/BurstLen/zero-transfer 参数，也不替代 AXI/错误时序动态验收。

## 参数和合法事务不变量

原 wrapper SHA a82bc50fac9b29df3f5f68527361f9dfac4792dfea3178b84eb488428d8d12c0，66–71行：DataWidth512、AddrWidth64、UserWidth1、AxiIdWidth4、NumAxInFlight4、BufferDepth3、TFLenWidth32、HardwareLegalizer1、RejectZeroTransfers1、EnableCompute0、NO_ERROR_HANDLING。57–63行固定 AXI、INCR、src/dst max_llen=4、reduce_len=1、compute.enable=0。未覆盖 BurstLen，继承8。

实际 generated SV SHA b6423c42b193e9e96416f65b9cea01cc85b8c035693b173547f25a2fbed7f7c2。3975–3988行得到 StrbWidth64、OffsetWidth6、PageSize4096、PageAddrWidth12、page_len_t13bit。4025–4065行读/写 splitter 的 not_bursting=0，reduce/max_llen来自 opt_tf_q。4204–4223行 opt从 wrapper请求装入；有效事务中 pagewidth=6+4=10，因此虚拟页1024B。

8559–8584行 RejectZeroTransfers 阻断零长度 req_valid，产生错误响应；合法非零请求才进入 legalizer。4108–4139行 num_bytes=min(剩余length,页余量)，严格分支 length>possible 才做减法，余量一直为正；最后一块清 valid。4319–4326行输出meta valid受 tf.valid、ready、!flush 限制，reset TF.valid=0。无效/复位周期组合 len 可能由0-1产生全1，此值不作为有效AXI事务发送，不能把该周期当成溢出反例或声称组合信号全周期≤15。

## 23条 WIDTH 逐组解释（精确逐条索引见JSON）

1. generated:8283 WIDTHEXPAND，BurstLen int unsigned=4'd8：4→32零扩展，精确8。
2–3. common_cells/cc_passthrough_stream_fifo.sv:81/100 WIDTHEXPAND：BufferDepth3，PointerWidth=clog2(3)+1=3，低2bit读写指针与unsigned Depth-1=2比较。正常复位及wrap维持0..2，扩展比较不改值；不是索引宽度丢失。
4–5. idma_axi_write.sv:125 / idma_axi_read.sv:101 WIDTHEXPAND：unsigned tailer6bit∈0..63，StrbWidth64-tail∈1..64。32bit减法完整表示；tailer0表示整拍边界，mask逻辑如何选用是数据通路功能问题而非此次扩展错误。
6. page_splitter:34 WIDTHTRUNC：OffsetWidth6装4bit，精确6。原rw_axi路径not_bursting=0，该支仍单独安全。
7–8. page_splitter:38 WIDTHEXPAND+WIDTHTRUNC：max_llen3bit∈0..7扩为unsigned32；当前wrapper得到6+4=10。即使同DataWidth下允许任意max_llen/reduce，最大max(6+7,6+8)=14<16，故**先赋4bit再clamp12**也不丢位。若改成OffsetWidth≥8且BurstLen8，则先截断可能回绕，不能跨配置复用豁免。
9. page_splitter:54 WIDTHEXPAND：page_addr_width∈0..12扩展与循环i=0..11比较，无符号值准确。
10、12. generated:4111/4130 WIDTHEXPAND：13bit page余量扩到32bit length，分支保证被减数更大，结果非负。不是隐式13bit length截断。
11、13. generated:4113/4132 WIDTHEXPAND：13bit num_bytes扩到64bit地址，不丢数。64bit地址空间末端自然回绕不是该warning造成；实际映射允许范围须由Host/测试契约限制，未证明任意64bit地址可访问。
14–15、17–18. generated:4241/4269 各 WIDTHEXPAND+WIDTHTRUNC：设a=addr mod1024，o=a mod64，0<n≤1024-a，则1≤n+o≤1024-64 floor(a/64)≤1024，故floor((n+o-1)/64)∈[0,15]，装8bit精确。扩展6bit offset不改值。即使reduce关闭，4KiB页约束也给≤63；结论限定有效非零事务。13bit加法输入上界1024，未在右移前溢出。
16. generated:4261 WIDTHEXPAND：r_num_bytes13bit扩展与unsigned32 StrbWidth64比较，值不变。
19–20. generated:4380 两个 WIDTHEXPAND：ComputeMxdequantLengthFits断言内64bit显式cast除数/被除数按65bit上下文零扩展，无值丢失；原wrapper compute.enable固定0、EnableCompute0，此断言前提恒假。不得为了此项关闭全部断言。
21–22. axi_pkg.sv:203 两个 WIDTHEXPAND：largest_addr_t unsigned128，strobe_width unsigned16，128bit除法操作数扩到144以适配外层算术，零扩展不改变除法。strobe_width须非零（原512bit配置为64）；不证明任意外部调用传0的安全性。
23. generated:8762 WIDTHEXPAND：NO_ERROR_HANDLING分支 idma_rsp.pld68bit=1'b0，零扩展68'b0。当前wrapper另行粘住AXI fault，不能把NO_ERROR_HANDLING理解成已经验证错误时序。

## PINMISSING：真实库接口遗漏，但未证明在选中top中可达

axi_stream_cut.sv:41 对 cc_spill_register 缺 clr_i；后者:23是输入，:38继续传入flushable。若这个模块被实例化，不能依赖悬空输入/二态初始化当正确行为，应在未来独立上游patch副本明确接 1'b0（常态无clear）或接设计clear，先审后改；不修改当前冻结provider字节。

本次词法已知module标识符传递闭包见 LEXICAL_REACHABILITY.json：从原flat wrapper到rw_axi backend、legalizer/transport、AXI读写/dataflow及cells，共21个名称（包含EnableCompute=0的未裁剪compute分支，属过近似），没有axi_stream_cut。直接命名该模块的父候选为 axi_stream_cut_intf / axi_stream_multicut；固定rw_axi body没有这些实例。词法法未展开宏，不能称完整可达性证明或elaboration PASS。

建议独立wrapper门仍保留官方294 source顺序，并采用**唯一精确 PINMISSING waiver**：仅固定SHA的 deps/axi_stream/src/axi_stream_cut.sv 第41行、规则PINMISSING、目标top固定 idma_backend_rw_axi_flat_wrap。记录这是解析未选库模块的接口欠债，未来top/profile变化必须失效。若独立实际elaboration显示该模块可达，立刻取消豁免并修独立source overlay，不能继续声称无关。

## TIMESCALEMOD 457 条

根因是混合有显式 `timescale 1ns/1ps 的冻结Matrix文件和无timescale的库/生成模块。固定5.032官方本机文档 exe_verilator.html SHA d9b6d4103c05fa890513e9e029bb597a0ebe51deb1eb4088c1e4b6b5e803f06a，--timescale条目2126起：设置无directive模块默认；--timescale-override条目2134起：覆盖所有source timescale。

建议统一策略 **--timescale 1ns/1ps**：保留已有模块显式时间设置，只补缺省；这是语义设置而非warning隐藏。组件wrapper没有时延行为，后续完整bench的时钟驱动仍要以其审定timeunit为准。若全体已有显式值均核为1ns/1ps且bench协议要求统一，可另审 --timescale-override 1ns/1ps；不要在尚未审全部时延/显式timeunit前全局override。是否消除所有457条须由获准后工具实际确认，不能静态宣布消失。

不建议457条waiver，更禁止-Wno-fatal/-Wno-WIDTH/全目录warning压制。官方文档2925起支持 .vlt `lint_off -rule ... -file ... -lines ...`。fixed_width_waivers.vlt.in只对23条涉及的精确规则/源行提出窄豁免，使用前必须核哈希+上述原参数；同一行两个同rule扩展可由同一行规则覆盖。它是待审候选，不是已生效文件。

## 独立原wrapper分层门（仅方案，尚未执行）

1. 前检原工具SHA619464a1…、官方927manifest+wrapperSHA、原294源/8include顺序及四initial defines；不重建/改provider，不加入Matrix/FMA/HostBench。
2. 用固定verilator_bin直接argv：--lint-only --top-module idma_backend_rw_axi_flat_wrap --threads 1 --no-std --relative-includes --timescale 1ns/1ps --Mdir <fresh-private>/obj；接精确审定.vlt、相同defines/incdirs、原294源、原wrapper。无shell/-f任意flag透传。
3. 资源不放大：继承210s总/180s工具、1CPU、4GiB AS、原16MiB实际RLIMIT_FSIZE，独立有界2MiB日志；原B2 receipt的128MiB generated_file_limit字段与native实际16MiB不一致，后继必须改元数据而不是默改限制。采用已审严格身份deadline/absence helper，工具退出后hash复核全部输入，任何新warning仍fatal。
4. 只有独立wrapperlint exit0、严格cleanup完成、输入postflight一致才称该top原参数语法/展开资格通过。无C++生成/编译/数值模拟。若出现新warning或资源错误，保留本轮原日志诊断，不自动再跑。
5. 真正AXI功能门后续应覆盖长度0/1/63/64/65/1023/1024/1025、不对齐、1KiB/4KiB边界、读写backpressure及early fault；另行授权。这里不把静态数值界证明升级为AXI功能PASS。

## Root 后续要求：优先去除未用库，而非 PINMISSING waiver

新增 **LINT_PLAN_REDUCED.json 为优先待审方案**：仅从官方294列表精确排除 axi_stream_cut.sv、axi_stream_multicut.sv 两文件，再加原wrapper，共293源。保留其余292官方源的原顺序、全部package/include目录、所有可能generate分支和原宏profile，不尝试激进压缩成21模块名单。两文件都是cut/multicut及其interface wrapper模块定义，未提供其他package；逐文件hash记录在新plan中。冻结源包字节完全保留，仅本次编译输入选择不同，必须另行审定这次subset，不能继承原294预处理闭包为subset已验证。

CUT_BIND_SCAN.json 对295源+admitted头文件（去注释/普通字符串）扫描：cut/multicut的字面引用全部位于这两文件内部，没有其他源的引用、没有字面bind/config。此前21已知module词法闭包也不含两者。宏动态构造的潜在模块名没有由该扫描求值，所以明确保留真实独立lint作为最终判据；若出现missing module/任何新warning，立即FAIL，不追加缺失stub或自动进一步排除。

该优先方案**没有PINMISSING waiver**。原LINT_PLAN.json全294+wrapper方案仅作保留备选；只有review证明保留全库必要且接受限定未达库定义边界时，才考虑其精确第41行PINMISSING waiver。没有把一般PINMISSING降级。
