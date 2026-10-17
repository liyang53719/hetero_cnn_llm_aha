# Seed BEGIN 结构反馈：最小源码候选，未执行RTL工具

原fullBench v4保持FAIL：AS6GiB下171.619秒bad_alloc，HWM6,419,521,536B；同时报告UNOPTFLAT。实际源/日志/receipt身份见SOURCE_PINS。不能宣称振荡bug，也不能把原运行改为PASS。

## 原依赖与二值固定点
MatrixPipeline115/121将allBegin聚合leaf.ready，再使leaf.begin.valid=ctl.offer&&allBegin&&selected。endpoint seed_active=front.seed_block；front95 seed_block含begin.valid，scheduler41/42用!seed_block阻断in_valid/in_ready；Matrix94 canIssue取allStepReady。array_control15 input_write是本拍issue，front87 fullquiescent包含!input_write，102 begin.ready再回allBegin。这是实际结构SCC。

实际Controller73 blockIssue=state!=idle||上游begin.valid||anyAck||poison；81 offer只在reserve。Matrix80 work要求!blockIssue。因此offer时work=0，所有issue=0，各ready不依allBegin；无offer时各begin.valid=0，反馈也断。状态0..7（含非法7编码）256组合验证此互斥，二leaf全部独立mask3072边界组合均唯一fixedpoint。移除interlock反例有两个stablefixedpoint，证实不能把高层互斥默默省略。8leaf沿相同二分结构推导，不宣称穷举全部8leaf状态或四值/X语义。

## 独立endpoint也必须安全
1024个独立endpoint布尔入口组合：外部begin/beat/commit、step_valid/ready、retained_quiet、reserved/ack/poison/abort。scheduler的seed_block直接包含begin.valid，无需高层Controller假设。因此begin.valid=1就使本拍issue/input_write=0，原begin.ready的!input_write冗余；begin.valid=0时改变ready不改变fire。所有旧新begin_fire一致，同edge begin_fire与arithmetic issue互斥。这里是组合边界模型，不是完整RTL/FSM或动态协议验证。

## 候选仅改一个生产provider文件
新增组合wire begin_quiescent（无寄存器），仅begin.ready用它；它保留busy/out_valid/array_out_valid与pre/mul/post/output_write全部已接受流水保护，唯一不依赖本拍input_write。原fullquiescent、fault/reservation/beat/commit readiness、ACK/sticky poison、seed_hold都原字节保留。array_control16-19后四write来自寄存valid；busy来自scheduler busy_q，out_valid由完成token/FIFO寄存状态决定。已接受流水不能被begin意向冻结：hold仍仅reserved||ack。

新增资源：0寄存器、0payload、0MAC/FMA、0端口、1组合资格wire；可能优化共享已有quiet项，未综合不声称零门面积。enabled=false原generate分支未改。无额外周期，实际数值/协议仍未验证。

模型含partial selected、某leaf仍在流水而全体不接受、abort/poison/heldACK、127次静态背压边界。它不是127拍状态仿真。beat/commit结构关系单列：reserved_q已经直接seed_block并禁止issue，fullquiescent仍用于其ready；本候选不预防性修改它们，后续实际工具若另报再逐路径诊断。

原文件只读；PATCH.diff及source是隔离候选。先review/root批准后才考虑单endpoint与完整307provider的新资格，不能本轮直接重跑大lint。复现：python -B test_cold.py，python -O -B test_cold.py；replay.py只生成一文件隔离副本，完整sourceclosure需在后续方案重新pin。
