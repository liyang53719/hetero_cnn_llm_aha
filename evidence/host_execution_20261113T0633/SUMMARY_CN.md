# 06:33 实际工程快照（INCOMPLETE）

- 原 O1 作业 98883 已明确超时 exit124（300.365s），对象0字节，未重复编译；原 O0 仍可用。
- 同一固定4096候选 Host 已完成 profile0/1/2 严格准入与非法opcode取指拒绝，非数值通过。105断言、17真实native保留。
- 本轮0.8B L0/L3使用原M128命令及描述符，各197周期/16读beat，其中真实BF16输入4×64B；issuedJobs1、pc0、无写回，无首算子完成。原17681/8855均exit0。
- 完整状态基线settle候选：512 idle输出及439周期Qwen2真实前缀差分一致，低相eval2048降至1538；活跃耗时未证实改善，TEMP，不迁移生产。
- driver新增全字段预检后一次提交，4个坏字段负例均无部分写入；仅driver单元范围。
- 35B两profile审计明确须role7双descriptor与独立2048×32只读physical映射、6MiB DDR phase arena，L0另需53,739,520B chunk scratch。原metadata与6负例符合预期，真实payload仍缺；不放宽Host准入或修改路由契约。
- 五块128完整原Chisel数值0/5；原head4 underflow FAIL保留。未开始同刺激完整RTL回放；完整block有效MAC利用率未实测。
- main基线d046733c，CI43373373823 success仅Git payload guard。工作树干净。临时清单已核，清理0，保留运行依赖及唯一证据。未知旧Host未重启；源码/权重/原日志未上传。

补充：transactional drive合入独立settle候选后，12真实reset/idle周期before/after输出与基线一致；仍不冒算术fatal或数值通过。
