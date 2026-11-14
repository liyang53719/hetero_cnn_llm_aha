# 2026-11-14 16:33 hetero：新Host LLVM生成，完整数值INCOMPLETE

## 实际工程
- 沿冻结before_cse新身份87554分段采用已微型验证的array合法化次序：hw-convert-bitcasts先于arc-lower-arrays和remove-i0。合法化6.01s、状态分配2.77s、LLVM方言lower13.92s均exit0、verify-each保持。此执行候选省略优化CSE，未冒完整等价，未修改数值精度或删除严格条件。
- 原59033将完整Host译为LLVM IR，6.38s exit0。后续llc -O0在120.01s超时，host.o为空，未链接运行。保存全部源码/IR/失败日志，不盲重试同命令。IR共有606函数，eval561214行，仅编译规模线索，不是已证明超时根因。
- 新layout从本轮已分配IR提取：1607504字节、85端口，不能套旧1607520布局。与官方微型state-file一致，3提取负例测试通过。保留106 strict sites、17 sink；17 source符号共有26调用点，与输入IR一致，要求同eval冻结只读而非限制只调用一次。
- 真实shared17算术联合测试exit0/0.857s：8×512 Matrix、8真实ICG每4拍门控1拍、真实但空闲DMA。180周期、618背压检查、6120冻结快照检查，512路输出各为3、6、…、24，8端点各一次命令/步/输出/完成。仅单FMA/门控联合资格，不是active DMA、Host、完整block、fatal或恢复资格。
- 新12周期reset/idle Host驱动及严格链接门禁已编写并py_compile，依赖当前layout和真实17；因host.o空，拒绝链接，未执行，不冒PASS。

## 身份与五块
- LLVM IR SHA256 4edb3f8e9d69973d2408740eff42302582278e76041a30587208c21a0e092828。
- 新layout SHA256 3b88cdb8c9b1cf26815d2fa5beb1bbef7fdbe4f3c393d60ddadd57b22e1b0627。
- shared17联合结果 SHA256 e37fef35b7ce83a648a98cbb2a60902457ce99cf198a9c450a197444c26242a4。
- 五块完整128原Chisel数值仍0/5：Qwen2、0.8B L0/L3、35B L0/L3。固定4096不缩减；原strict下溢FAIL、35B缺真实权重/契约/准入保持；新恢复候选尚非最终完整统一源。完整RTL及完整block有效MAC利用率未测。
- 旧37765终态未知，不重启、不继承丢失50行。新87554/59033均已有终态，不把Unknown当停止。

## 下一步与维护
- 定位llc大函数编译成本，安全限定新编译策略；对象有效后才能执行新reset/idle与真实输入，不反复重算前缀、不预装参考、不放宽异常。
- 本轮起始远端1bbd3e4b25d1b50ee25e8d40c38b135daae02d9e，CI43611387874成功（payload guard）。本地54776eab工作树干净，未用陈旧树覆盖main。
- 临时清单已核，当前源码/IR/库/布局/测试仍被依赖或为唯一证据，清理0。只提交允许摘要/中文计划，无权重、NPZ、IR、检查点或被拒源码上传。
