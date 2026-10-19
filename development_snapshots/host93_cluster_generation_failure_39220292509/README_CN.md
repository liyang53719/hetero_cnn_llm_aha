# 39220292509：cluster 生成诊断原始 FAIL

- 唯一 run 39220292509 / job 117953745706 / attempt 1，提交 0a1c06be997dfab3e93c8c8b672575ff70e149ba。整体 INCOMPLETE / FAIL，总 574.048876 秒。32 个 native 阶段中 31 个成功；末 host93_cpp_generate 自然 exit 2，97.573698 秒，未超时，cleanup_confirmed=true。
- 原始三份 JSON 逐字保留。FIR 恢复历史 size/hash；工具 build/tiny 与 fresh_host_sv 为 true。cpp_generated、cpp_compiled、reset_launch、n0_numeric、weights_loaded 均 false。
- 完整有界 merged log 扫描 4001 B，SHA256 a19c7e174ad6bf088b0be43f75af3b9cbb5d609c00f414bab9ab03214c55afd1：1 个 UNOPTFLAT、2 个 error header（含一条 1-warning fatal 摘要），0 未解析/记录省略，全部 9 个 Example 坐标保留。全局 header 与 fatal warning 数一致，但多进程归属仍 NOT_AVAILABLE。完整日志不发布。
- 前次 39204020851 的 35 个 UNOPTFLAT 降至本次 1 个；本次仅 idma_axi_read.sv:87:12，9 个 Example 经 read:169、generated:132、派生 FIFO:74/39、read:88/168 返回 read:87。原安全记录精确 source ID/hash 是坐标依据，未从去敏尾恢复私有层级名称。
- 实际 cluster wrapper 有 18 个 combo 输入、2 个输出、6 个 DPI import、1 个 combo import/call 点、2 个 always_comb；唯一候选与 top 引用可见。makegraph 只观察到一个匹配的 archive 规则，不能表述为已编译库。specialization 为 UNKNOWN；依赖结论 NOT_ESTABLISHED。
- root_header_state=CONTRACT_ERROR 且 identity=null，handle 数未知，expected_structure_observed=false。按固定代码控制流，首次 _read 未成功返回，root header parser 未进入；直接文件缺失应记 MISSING。现有三 JSON 不能区分 regular-file、4 MiB cap 或同fd稳定性合同等具体读取门，也不能把未知的 256 实例倒填成事实。
- 固定 FIFO ready_o 的方程不直接依赖 valid_i；当前 state/data always_comb 同时读 valid_i、写 ready_o，支持过程依赖过聚合的有限候选解释。真实 SameCycleRW 时 ready_i→ready_o 依赖必须保留。下一最小候选为将 ready_o 原 procedural if(flush) 两分支独立，保原指针比较和四态，不改 iDMA 原子 gating。尚未运行新拆块。
- 旧真实 FIFO 4/5180 只验证先前 valid_o 拆块的抽取组合逻辑和手动状态；新 ready_o 拆块必须重新通过同一四态矩阵/背压用例，不能继承旧 PASS。无 FF/reset/delta-cycle 或完整行为等价声明。

本轮 actual 独审已接受有限失败证据：review_cluster_generation_actual_39220292509_20261019T0821；MANIFEST1728B/eb09e9bd53bba6456b898b693d6f753b23fd2a1599d6668e13c6335a252457b2；SUMMARY8177B/924da874fe0c25f3f3af51d2ab8b534ed6d6e33f3b913d09e9045eb4b72eadb8。判定 PASS_ACTUAL_CLUSTER_FIFO_GENERATION_FAILURE_EVIDENCE_ONLY，不授整体成功。原 FAIL 不改，不新增 warning 豁免或资源额度。
