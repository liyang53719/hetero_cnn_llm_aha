# 首次 cluster Host 编译与原短 reset/launch：有限实际成功

原 run 39232100796 / attempt 1，源码 commit `29e0c301d9aaddfee8bcf9deab6d7aa2d24c7a16`。Actions 已 completed/success。原协调器状态为 `READY_REQUIRES_ACTIONS_EXIT0`，模式为 `host-cluster-reset-launch`；本目录三份 JSON 保持原字节。

- 总墙时 870.427722 秒；37 个 native 阶段全部自然 exit 0、cleanup_confirmed=true、无 timeout。同一 job 复用新 FIFO 前门、工具及生成物，Host C++ 生成 123.743956 秒、编译/链接 56.433910 秒、短 reset/launch 0.055328 秒。
- 新 ready_o/valid_o 双拆块再次通过真实 Icarus 抽取组合四态 miter：4 cases / 5180 comparisons。此资格限原参考与派生组合方程、手动状态矩阵及背压轨迹，不包括 FF/reset/delta 周期或完整生产数值等价。
- 原工具 build/tiny 与 fresh Host SV 通过；FIR 42417256 B / 264f8b3a11c02d0d0917001f1d69452ec1c1294c426c9c81e1e577cdc523385a，SV 76366612 B / 2fcc1ba70ad3406b967292624329593aa38e3fe562e9ff3ac675eec100562f61，保持历史精确身份。
- generation 合并日志的完整有界扫描为 1872 B / 3fa42ee18387e696c31810afdaaba4c8e3d42ab619d7b64b1e0fc6382ca2a884，0 warning / 0 error / 0 unparsed，记录和 Example 无遗漏。warning-fatal 策略保留；该结论仅属于本次生成日志，不是所有阶段日志全文或全设计无环证明。
- 当前固定源码要求真实 retained13 的 seed=1 特化参数、对应 SHA512 名称前缀、当前 args→wrapper→初始化构造→archive/ELF 链、原 83 个顶层端口，以及编译/运行前后输入和生成物稳定检查。成功返回建立该有限源码合同通过记录；未上传私有 args、生成源码、archive 或 ELF，本文没有对这些私有现物做独立重读。source_hashes 报告同 job Host ELF 为 13323224 B / 9bda15e2efa466a55632d34bd1aeba21d223102a88e47618fe975247fad56aba。
- 原字节 short_launch.cpp / launch payload 只做 reset asserted/released 各 4 个高边沿，再在最多 16 个候选边沿中等待第一个真实 launch 握手；该边沿之后不再 eval，也不显式调用 final。源码成功路径精确检查 RESET_OK、LAUNCH_OK、SHORT_PASS 三条 marker；成功 raw native log 未上传，本文不冒称独立重读 marker 原文，也不倒填具体握手边沿值。
- AXI 输入 ready/valid/data 保持零，没有提供 RAM/AXI 响应、加载权重、完成后续命令或进行 N0 数值比较。普通 C++ 对象析构不扩展成完整协议/终结资格。原 summary 的 cpp_generated、cpp_compiled、reset_launch 以及 toolchain_build、toolchain_tiny、fresh_host_sv 共六项为 true；n0_numeric、weights_loaded 仍为 false。完整 block 数值和全长回放均未获资格。
- 安全 census 仍仅观察 cluster wrapper 18 个 combo 输入、2 个输出、6 个 DPI import、1 个静态 combo 调用点、2 个 always_comb 和 1 条匹配 library 规则；不能据静态调用点推出动态调用次数。其 specialization 公共字段仍 UNKNOWN，不用它改写已执行私有 gate 的范围。
- root header 仍为 5296945 B / 82307c51e8722e51062eaf38200355143d5e86cdaa50fdd4f0c9d24e0c458ef6：首次 SIZE_LIMIT 后有界重读成功、final_code=OK，解析仍 UNRECOGNIZED_SYNTAX。两个 handle count 保持 null，expected_structure_observed=false；没有把源级 256 实例期望伪填为实际 handle 证明。

独立 actual 审身份：review_cluster_reset_actual_39232100796_20261019T1006；MANIFEST 1066 B / fa51d430f3851a556b7c6f2472e1ddb3f6e475c43abeabcdde86958801f5b22f；SUMMARY 11813 B / 120ffd07a662deb267be143b1c890c87d787637e2ac8d50da91c79a8963edbb3；verdict PASS_ACTUAL_CLUSTER_HOST_COMPILE_AND_BOUNDED_RESET_LAUNCH_ONLY。本小批仅保存三 JSON 和安全范围说明，不修改源码/workflow、不触发新的 Host/native 作业。完整 Actions 日志、私有 native log、生成源码、工具/模型二进制和机器库存不进入仓库。历史失败和之前 generation-only 的 scope 原样保留。
