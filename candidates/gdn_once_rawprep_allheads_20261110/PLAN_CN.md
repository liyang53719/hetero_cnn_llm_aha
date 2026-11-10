# 单次 RawPrep，同实例全 head 调度

- done：RawPrep一次写16heads的128-token prepared后，复用同一原cold/state、phase1–17 owners及scalar/bank，串行完成head0和head1各两chunk；head切换无reset/不重跑RawPrep。heads2数值PASS，共1,708,032个32位字。
- ongoing：同一硬件headCount运行输入=16的80M-cycle/3000s有界回归。仅结果终态后更新PASS，当前INCOMPLETE。
- todo：完整投影/完整block，统一4096MAC五块模型128后冻结同刺激RTL。五块仍0/5，未报告80%/90%利用率。

只验证合成Conv/QKV/AB边界，不是训练权重完整block，不是生产Guard/lease或最终共享4096MAC硬件。新调度改变SV，旧单head PASS不可直接迁移；heads2已用新SV重测。Chisel实际发射SV并用Verilator执行，非纯解释模型。

计数说明：末行旧executeVectorCalls/phase17FormatCalls标签值为每head，不是合计；每phase计数已在每head实际握手时断言，heads2合计2,637,824与2,048。

无清理、无删除、无NPZ/权重/TSV上传；所有生成数据本地重建。历史PID40532仍EXIT_UNKNOWN未操作。
