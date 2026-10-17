# 一个 query/KV-head 组的地址与寄存器映射

范围：Qwen2 H1536、12 Q-head、2 KV-head、headDim128、query0..127。只给整数映射与最小接线方案；没有数值执行、RTL/EDA、周期或80/90验收。脚本can_supply恒False。三种地址空间必须分开：DDR字节地址、Q-local SharedL2、Dense A-bank raw scratch。

## 现有QK16端口推导

钉住的QK16 Qwen2Block.scala:55–59要求externalMatrix/256列；:121–125已有denseWindow[16][16] FP32和denseWeights[256] FP32。:508–510只把当前query/head的Q128词放进local line0..7，不是六head Q缓存。:323–327是memory/local握手，返回成功才更新packet/av。

令global head H=6*kv+h，h=0..5，d=0..127：
- Q DDR byte=owner.a+4*(query*1536+H*128+d)。64B beat从d向下取16词边界，beat lane=d%16。
- K/V DDR byte=owner.b/c+4*(key*256+kv*128+d)。DDR物理bank映射没有源码证据，必须保持unknown；不得套用片上bank公式。
- Q local line=floor(d/16)，SharedL2实际16×128bit memory，bank=4*(line%4)+floor((d%16)/4)，row=floor(line/4)，bank内FP32 lane=d%4。SharedL2Fabric.scala:27–29,53–68。它与下述16×256bit Dense A-bank是不同物理资源。

QK组key_start每16个key取一组，count=min(16,query+1-key_start)。每组8个depth步d0=0,16,...112。每步先local-read Q16，再逐key接受count个64B K响应，存denseWeights[16*j+i]，所有活跃项到齐才attPackedIssue（:517–532）。尾key的B显式置0，不读旧寄存器（:210）。A[i]=BF16(Q[d0+i])；B[16*j+i]=BF16(K[key_start+j,d0+i])。

MatrixPipeline.scala:145–160按endpoint e取B[32e..32e+31]，A16广播；物理每endpoint是16×32。被选有效partial为result.row(i).col(16*j+i)，对应endpoint=floor(j/2)，endpoint_col=16*(j%2)+i。8 depth步保持原ordered FMA；每score随后按i=0..15有序Scalar Add并scale。没有六head并行Q供数，不能绕过原Scalar/SFU瓶颈。特别注意：此QK16源码:544–546是Legacy fold→scale→score，没有snapshot:47要求的BF16(dot)及BF16(score)边界，两个数值policy不等价。本包仅核映射；项目已有可复用的attention_qk16_bf16_materialize/qk_materialize.patch（SHA c4f826e2ba76848f80dd7f631fc20501b88ef3a591549ab002bc0b140d103775），已提供dot BF16→scale→score BF16及finite检查；另有attention_qk16_host_selection/selection.patch传播选项。两者默认关闭，已有classcompile记录但未闭合完整Host数值接线。后续应复用已审补丁而非重复实现；不能把Legacy缺口说成项目没有方案，也不能因“有序Scalar”就声明数值等价。

## 六行scratch：已有source candidate，production未连

score line=4096+8*h+floor(key/16)，prob/exp-weight line=4144+8*h+floor(key/16)。一条line为16 FP32词；word=floor(line/8)，bank=2*(line%8)+floor((key%16)/8)，bank内lane=key%8。

因此score word=512+h，prob word=518+h；同key-block的六head落同一bank pair、不同word，需要六次64B事务，不能六head同拍银行读取。96line共6KiB映射无alias。raw写是接受边沿直接写两bank，非FFN tile跨边RMW。写成功matching ACK之后才发布有效位；读须generation/query/kv匹配且written。原DDR KV、raw scratch与Dense/tile lease冲突必须由原parent处理。

scratch.patch确实提供默认关闭的Chisel源扩展，但冻结production未包括它；需raw_kv补丁链、scratchBegin和完整matching key接线，不能把孤立patch当已运行工程。旧Qwen2Block scores/probs SRAM未因此消失，本方案不默认为可同时使用的第二缓存。

## PV：384B panel与V128的最小寄存器别名（全部待接线）

旧attention_bank_panel模型曾建议denseWeights上96词别名，本片独立选择denseWindow以避免QK全256词B ingress的存活冲突；两种别名不能同时计成两个panel。

复用已有denseWindow[0..5][0..15]作为96词/384B exp-weight panel；另外denseWindow[6][0..5]保存六个inverse，共102/256个现有FP32词。inverse不是panel内免费值，也不能放到仍被后续QK覆盖的acc里。其余Dense窗口词不被假设为额外cache。这只是源码级不增加payload数组声明的复用设计；选定实际组合是否保留这些寄存器、综合是否已裁剪及最终物理inventory均未验证，不能把重新激活的dead flops当免费物理资源。denseWeights[0..127]装当前key的V128，来自8个真实64B DDR成功response.fire；其余B[128..255]=0。

每key k：A[h]=BF16_RNE(FP32_Mul(panel[h][k%16],inverse[h]))，h<6；A[6..15]=0。B[c]=BF16_RNE(V[k,c])，c<128。四endpoint sliceMask=0x0f选通，result.row(h).col(c)即六head×128输出。物理仍八endpoint×512=4096 MAC；不得将利用率分母减成2048，也不得把空闲endpoint分配给第二group而忽略现服务独占。

独立算法证据为已发布composed schedule snapshot:55–84：panel存exp值；每head按key有序sum、一次inverse；每key先weight*inverse并BF16，再V BF16进入FP32 FMA；key按0..query严格增加，同context clear仅key0，last/emit/finish仅query。最终所有selected cells检查后逐64B输出BF16，所有DDR写成功ACK之后才consumer result ACK。此映射脚本不执行/重定义这些数值操作。

## 生命周期与冲突

1. 独占一个(query,kv,generation) scratch上下文。按钉住snapshot先逐head完成全部六行QK，再逐head完成六行softmax，Q-local128词只复用当前head；softmax阶段inverse[h]逐个存入窗口row6。score/weight写的clean ACK不能省略。
2. 取得denseWindow和denseWeights整个组的独占lease，排除Dense window clear、ordinary Dense/FFN复用；当前QK只在packedBusy断言排除denseWindowGot，PV全过程需扩展同一guard。
3. 每16key边界，从六条prob line逐条read/response/ACK填panel六行；尾块inactive key不供数。必须六行全部完成再使用，不能有默认ready。
4. 每key依次完成8次V DDR响应，再供A/B并保持到Matrix step.fire。V寄存器允许在该step被接受后填下一key；panel只有本块所有活跃key step被接受后才可覆盖。此为同一独占lease内更新，不是把物理寄存器提前归还另一owner。下一key的六次FP32 normalize必须经同一共享Scalar的合法仲裁与matching ACK；若使用pause/stepsDrained，保持同一PV group/context。step.fire后的寄存器可更新并不证明Scalar/Matrix可免费重叠。所有返回延迟均未知。
5. 最终Matrix结果保持在原FIFO head，输出48个64B beat（6×8）逐个写ACK；最后才result ACK及matching done/completion排空。denseWindow/denseWeights租约直到结果ACK并完成group终止后才可交给其他owner。
6. abort禁止新接受，不取消既有bank/DDR/Matrix债务；保留租约直到匹配排空，清scratch有效性，不能以软件callback结束代替ACK。

## 最小Chisel owner接线顺序

A. 控制/别名片：在原Qwen2Block denseWindow/denseWeights处加默认关闭、互斥的Attention组lease与panel/inverse别名访问；不新增payload阵列、不改FPU。明确QK16/原Dense/PV互斥与所有复用点断言。
B. scratch片：接已有raw scratch ABI及generation上下文；将六行score/weight写读与实际ACK连接。保留每输出Scalar加法/乘法顺序，同时复用已审materialize/host-selection补丁显式选择snapshot官方BF16(dot/score)边界；exp/sum/div顺序不变，先不引入16lane softmax borrower，也不声称80/90。
C. PV供数片：原attPVStart/Read/Scale/Compute附近增加panel六read gather、V八read gather、mask与pending-bitmap控制；保持FP32归一化和原BF16边界。PackedAttentionStreamClient.start.pv目前硬接false，单独增加pv=true路径；其count=query+1、index=key、sliceMask0x0f控制已有，但它没有operand payload存储。
D. 退休片：不复制结果tile，逐行/列从现FIFO head选择；48个输出beat ACK之后才assert result.ready并完成fire，matching done后release。接入已审单池metadata模型时接口仍标candidate，真实trace前can_supply继续False。

本包7个normal/-O冷测穷举Q/K/V地址、Q-local128词、96scratch line/1536word无alias、QK256选中对角、PV768选中结果及query0..127尾块。它证明整数索引，不证明端到端供数、timing或数值。
