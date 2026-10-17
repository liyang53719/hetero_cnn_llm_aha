# 原wrapper v3：最窄内部拆分候选，未执行

原v1/v2保持FAIL。v3只撤掉v2不受支持的top public split，改精确非top idma_axi_write.write_req_o；新增cc_passthrough_stream_fifo.ready_o赋值隔离。保留4原isolate，总6个精确module/var目标。源码/端口ABI没有变化。

官方V3SplitVar.cpp L182拒public、L1166内部IO连接；Verilator.cpp L253 split早于L298 inline。来源、Git blob、快照SHA及限定行见OFFICIAL_EVIDENCE.json。这个顺序只支持候选合理性，不保证后续alias不重合并。所有规则要匹配唯一固定源module/decl，否则preflight FAIL；实际SPLITVAR/UNOPTFLAT/其他新warning仍fatal，不压制。

293源/1039完整pins/原wrapper固定参数/21WIDTH精确规则和helper字节均继承已审v2；210s总/180工具/CPU1/AS4G/FSIZE16M/log2M/64M输出树采样软限不变。helper保留原leader身份WNOWAIT+strictcleanup。启动前调用者检查内存和无其他重作业；失败不自动重试，不涉及wholeBench/数值。

位依赖证明：FIFO ready_o只Q/flush/ready_i/valid_o，没有valid_i；内部write_req_o.W.valid流向coupler，AW.valid回写另一字段，拆分只改变工具内部调度分组。原证据见idma_wrapper_unoptflat_diagnosis_v1_20261017/V2_REMAINING_CN.md。元数据记录声明匹配，不伪称工具内部命中计数。

待root单次GO命令：python3 idma_wrapper_lint_runner_v3_20261017/run_lint.py --workspace "$PWD" --out "$PWD/idma_wrapper_lint_attempt_v3_20261017" --execute
