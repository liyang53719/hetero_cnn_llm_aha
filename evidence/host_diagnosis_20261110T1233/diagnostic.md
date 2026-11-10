# 原 Host 分阶段诊断：FAIL 清理崩溃 / 完整数值 INCOMPLETE

原 session65749，固定同4096硬件及4GiB/单CPU配置，新增诊断而非无证据重复长测。Elaboration 10.09s；lowering 113.21s完成；官方PrepareAst后265.19s进入engine。之后连续样本为Module结构hash→HashMap.get→SymbolTable.scala408 lastStopSymbol.get(module)，350–400s约50s用户CPU、堆稳定；峰RSS4467396KiB。

最终原任务600.033s退出-6，timeout=false：SymbolTable输出dma.backend.model.axi_read_rsp_i__r_last依赖环，finally清理在native cluster::final SIGSEGV。不是runner600s预算杀死，不能将该终态记成超时或数值FAIL。未构造完成、未reset、未发射prefill。完整5块M128仍0/5。

环来自字段拆分后再cat的整个UInt依赖污染：ar_valid→packed read request→r_ready→r_last→packed read response→rid→ar_valid。不得删合法r_ready→r_last，也不能套历史clock-boundary修复或AllowCycles。需要保持位值的cat/bits精确化并重验全部调度契约。

native清理缺陷已独立复现create8/no-eval/destroy SIGSEGV，候选只按初始化状态选择final，不改RTL；见native_cleanup。纯Module结构hash缓存候选保留equals、未混旧clock行为，只有小图资格，不继承Host PASS。原运行和原库保留；prepared hash Host未启动。

已提交191893a的输入桥/转换参考审计CI42817960064 success仅payloadguard。其RoPE与独立参考1024×64 cos/sin全字节一致，不能将格式桥称AXI时序已验证。

运行日志、GC、进程采样保留；JVM原错误报告本地保留并以摘要/哈希记录，不上传生成IR/classes/库或数据。
