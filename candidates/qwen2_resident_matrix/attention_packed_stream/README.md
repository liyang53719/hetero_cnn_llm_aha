# 默认关闭的 Packed Attention stream client（源级候选）

已实现：独立 Chisel client 源、严格零fuzz服务状态补丁、控制模型与冷测。已完成：独立源评审及19+19冷测。待办：Scala编译/RTL单元、接入原mode0 Attention owner、raw bank/384B panel、完整同激励Public程序。当前没有运行EDA、数值任务或宣称硬件性能。

## 端口与债务

client直接复用MatrixStreamPort；enabled=false时所有请求/ACK保持无效，不接受任务。启动描述符为tag/pv/count，QK count1..16表示本tile合法keys，固定8step；PV count1..128表示本query合法keys。输入index必须单调，clear只在0，last/finish/emit只在末次。producer负责BF16 operand构造并在未接受时保持稳定。

结果直接指向已有两槽FIFO的head，没有16KiB复制。consumer在完整score/raw/output写匹配ACK后才给result.ready；selected finite检查和BF16转换由后续owner实现，本client只检查context/last/protocol error。不应把该client单独宣称为数值故障闭环。

abort阻止新step/public result，排空已接受result与匹配tag的done，再输出error completion；completion采用可取消的Decoupled契约（不是Irrevocable）：直到ACK为止，abort可把error从false升级为true，tag不变；同边沿abort+ACK只接受error，随后锁住。已ACK的输出写不能回滚。foreign done不能退休当前债务。错误之后锁住至硬件恢复。全局reset需系统保证所有下游域已恢复；operational abort不能用reset代替。与done同边沿abort不得丢失已消费完成事件。

PV key16 pause期间不发step。仅在实际服务metadata queue已空时给pauseGranted：新增默认关闭enablePackedDrainStatus输出从现有tags队列导出，不新增队列、计数器或payload。必须连接同一个service输出，不能接外部“已排空”常量。status没有代替group/result/done债务，group/context在pause期间继续归client所有。

## 源与资源

先对原MatrixPipeline/BurstProtocol应用已存在retained_accumulator_seed（含真实endpoint/leaf）、combined_service和service_seed补丁，再应用本补丁；原Dense/seed路径与default参数保留。kernel selector接线尚未添加，未来必须按原legacy client的normal-layout映射连接optional Dense/seed字段，不能改Dense的路由。

client仅4个寄存器声明：state3bit、descriptor41bit（tag32/pv1/count8）、index8bit、poison1bit，共53控制bits（编码/综合结果待验证）。没有operand或result寄存器。model的统计计数器仅测试ghost instrumentation，不作为免费RTL寄存器。原service仍有5累加context、8 metadata slots、2结果tiles；本client保守只使用context0且不并发多个group。额外selector/mux、panel384B和bank/Scalar资源不包含在53bit内，尚未实现。

小补丁只定义accepted-step、result-retire、matched-done和pause/abort契约。现有MAC array、golden与Host程序均未替换。正确的算术顺序和完整固定资源利用率仍需后续同激励实际RTL验证。

冷测：python -m unittest candidates.qwen2_resident_matrix.attention_packed_stream.test_model candidates.qwen2_resident_matrix.attention_packed_stream.test_sources；再以python -O运行。source prepare只调用patch，不调用编译器或仿真器。
