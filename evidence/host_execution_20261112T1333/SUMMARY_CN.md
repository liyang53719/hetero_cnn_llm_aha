# 13:33 原Host窄数组修复、真实Matrix库及输入/flags推进

1233现场保留。真实原array1失败已最小复现，40处窄array_concat改为位等价bitcast/comb.concat/bitcast，总位数和位序不变；全部6种实际元素宽i1/3/5/8/16/32，各8192共49152编译LLVM差分零差异，另2非法shape拒绝。105strict/17typed split不改，完整Host Arc原30976已终态exit0，实际生成LLVM23268257B；19callback符号/38调用site静态存在，未运行不推定边沿次数。后续llc -O0原91119在150秒预算内进行，未链接/运行。

原rev8b_b九源已递归找到，纠正先前只搜顶层误判缺失。补真实依赖后Matrix endpoint Verilator生成exit0/20.56秒，单线程80194编译、57456链接及实际8独立handle测试均exit0。8×512总4096定义未缩，reset/idle ready1/protocol0，非法count/reset、read-before-eval/unsampled clock拒绝，never-eval守护真实通过。libmatrix SHA03f101afa8c215c612ef6a46bd23d84f75f1890c369446ae17f65f4b70f7c507。仅ABI/resetidle，非数值/Host；ICG/iDMA/shared17仍缺，rawflags未暴露。

Qwen2冻结真实13raw→FP32及原cos/sin合并rope构成14段只读桥，21条命令/215descriptor二进制精确匹配历史pin，manifest文本不同明确记录。5项桥测试通过，无参考中间预载，无硬件变更/Host启动；0.8B复用1233两桥，35B限制不绕。

冻结真实Q/K RoPE及三路bias flags核查97532 exit0/8.65秒，共950272次原序add/mul：UF0、NX687674，五输出逐位匹配。普通scalar UF致错/NX单独不致错，未套用特殊opcode例外。仅该五阶段，Dense/QK/PV全FMA、RMS内部、softmax/SiLU/硬件传播仍未核全，不能冒完整flags通过。

五块M128完整原Chisel仍0/5，同刺激RTL未过、4096完整block有效MAC80/90%未测；原head4 FAIL保留，未知旧Host不重启。开工main3907fc19，CI43219898431success仅Git门禁。工作树干净，9.1GiB内存/57GiB磁盘，临时清单保存、清理0。仅允许摘要/hash发布，不上传源码、原始日志、IR、权重或生成数据。
