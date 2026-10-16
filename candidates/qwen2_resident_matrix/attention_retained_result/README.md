# 持有既有 joined result FIFO，消费后才 ACK

## 中文计划

- 已完成：QK在原结果slot保持期间执行fold/scale；PV在最后word完成BF16转换后才ACK。首轮M1/M2原owner score/output bitmatch。
- 已完成：8项测试普通/优化模式均通过，38项依赖/4项候选源身份校验通过，独立审查通过。
- 进行中：下一份独立候选的bank-backed score/prob路由与端口调度设计。
- 待做：score/prob和输入的实际bank布局/路由、真实selector/mux/flags连接、完整M128/整块/RTL验收。

此目录继承上一份controller的原算术顺序，只改joined result所有权和消费时序。没有修改此前候选、原owner、活动Public runner或硬件源码。

## 具体资源映射与信用

`MatrixPipeline.scala:16–22` 已有两个16KiB register-backed结果slot，FIFO仅暴露head，result.ready控制出队；group done等待FIFO为空(:58)。本模型只用其中一个slot，另外一个保持空闲；不声称已支持两个producer并行。每次Matrixgroup仍只用1context/1accepted step，其他context和metadata credit不用。

`TileView`仅保存controller引用和group身份，不保存/复制word tuple。每次读取直接访问当前MatrixPort.held.words；模型检查同一tuple身份保持不变。出队后view失效。新的Matrixgroup在slot未退休前被拒绝。fold动作原来保存的整个host tile现在改为这个live view。

QK的16个有序sum可拟复用 `Qwen2Block.scala` 的acc[16]；完成的score packet可拟复用tmp[16]；每次lane operands可拟复用av/bv[16]。这些已存在并被源门固定；本次仅给出live-range提案和最多16word消费约束，未修改真实寄存器mux。Norm/RoPE/Bias/Dense不能同时获得这些资源。

## 每cycle的实际模型事件

- QK同一个模拟edge最多从wide FIFO head选择16个依赖cell。每stripe的lane operands捕获后，Scalar packet接受、返回、数据保持、matchingACK；在全部16轮fold、dot BF16、scale及score BF16完成前，Matrix result一直保持，ACK计数不增加。
- 每次Scalar tick同时推进held Matrix slot一edge，确认无FMA重算、无payload变化、无结果ACK。Scalar result反压也延长Matrix slot占用。
- PV保守地每edge读一个选中FP32word并做原BF16边界；读完全部6×128word且最后转换成功才ACK。最后一次读/转换和ACK可记录在同一edge：先消费组合head再出队，不宣称多一个独立cycle。这是显式拟议selector/capture速率，不是测得的组合mux时延。
- `read_events`记录edge/group/index，`ack_events`记录edge/group/poison；它们和历史views仅用于host测试观察，不是额外硬件payload/metadata存储声明。
- 最多occupied=1、available=1或2；保守禁止held slot期间新Matrix issue。不能把空余第二slot当作已实现吞吐。
- early incomplete retirement、错group、未建模cell、每edge超额读、stale view均拒绝。计算失败排空Scalar accepted debt，然后poison-ACK已有Matrixslot；后续ordinary owner保持禁止。

M1读取1,728个joinedwords并ACK14次；M2读取3,648并ACK28次。Matrix步骤/selectedFMA/Scalar原语数量与前一数值候选一致，新增费用是持有期间的时隙和PV单word消费。本路径不读A bank，所以没有把FIFO读取伪算成免费的A SRAM端口。

## 仍然未放置的数据和下一路由门

Q/K/V输入、六head scores/probabilities/max/sum/inverse和最终输出仍有host存储，不能称完整物理模型。这里仅关闭“Matrix result在fold前ACK、靠无主host tile继续算”的缺口。

审计更正：原raw KV key实际是13bit，但请求和ACK都显式限制line<4096；不是12bit字段。物理word=line>>3，因此只到511。现有FFN tile route从768开始且rawlease期间禁用，不能用于512–523。没有现成合法raw-FP32 scratch路由。

可单独审查的新profile：score lines4096–4143、probability lines4144–4191，对应现有A banks word512–523，共6KiB。需要明确scratch region/generation、written-before-read、请求与ACK验证，不能索引旧4096-line KV validity或通过旧K/V地址核验冒充cache数据。默认旧line4096拒绝必须保持。

旧raw通道64B请求只触及2个256bit银行；无反压edge0接受、edge1held、edge2ACK、edge3下请求，最小II3。head-major布置下同keyblock的6head同一bankpair，绝不能称一cycle读齐；若保留6×64B概率缓存必须指定既有384B寄存器/银行及租约。上述路线仅是明确提案，本目录未实现、未计入性能收益。

## 效率边界与复现

沿用固定4096MAC、整块6,014,828,544 usefulMAC和原SiLU账本：M128的71,680SiLU向量及1,146,880division不能省略。所有ticks仍由显式假设Matrix/divider latency和捕获/反压参数生成，非硬件测量。没有80/90%验收。

`python3 -S -B -m unittest candidates.qwen2_resident_matrix.attention_retained_result.test_controller -q`

`python3 -S -B -O -m unittest candidates.qwen2_resident_matrix.attention_retained_result.test_controller -q`

`python3 -S -B -m candidates.qwen2_resident_matrix.attention_retained_result.check_sources`
