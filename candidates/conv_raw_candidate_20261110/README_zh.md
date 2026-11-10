# 原 Conv→RawPrep→两chunk：选定head数值PASS，完整block仍INCOMPLETE

原GdnRuntimeConv4OwnerRecoveredV7真实写回后，由status/historyCommitted/drained交接RawPrep，再执行head0两chunk phase1–17与state export。同一scalar/bank/memory；Conv输出不预置，消费要求已有真实写。上游DUT与n16 fatal0均未修改。

完整结果见NUMERICAL_SUMMARY.json、PLAN_CN.md、results/simulation.json：M128/head0，78,183,169 cycles，774,339 reads，104,320写beat逐项比对，exit0。Chisel实际发射SV并Verilator执行，非纯解释模型。

首跑driver采样顺序FAIL保留fail_first。修复为先驱动response再观察fault，前后同SV hash，不能说原DUT故障。

PASS只含合成Dense QKV/AB边界、合成Conv权重的真实连接子链，不含训练权重完整block、其他heads、4096共同Matrix证明、统一五块RTL或完整block利用率。原全16 underflow FAIL保持；五块128仍0/5。

复现：run.py --jar-dir <pinned jars> --verilator-dir <runtime> --head 0 --cycles 120000000 --wall-seconds 3600 --cpu-seconds 3300。默认8M cycles不足此新链；使用已记录参数，先核原运行身份，不重复启动。

下一步接真实Dense/RMS前缀及GatedNorm/O/FFN尾部，保持既有算术顺序。数据/IR/classes只留本地，源码包不含权重或数组。单scalar功能链不代表80%/90%方案。
