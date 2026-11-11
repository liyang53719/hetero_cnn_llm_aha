# 10:33 原数值链与真实native恢复

总状态INCOMPLETE：五块M128完整原Chisel数值0/5；同刺激最终RTL与完整block80/90%利用率尚无实测。原L0 head4下溢FAIL保留。旧Qwen2/L3会话终态未知，未重启，等待用户决定。

本轮开始核远端main47353232及对应CI42996991443成功（仅git-payload guard），本地旧checkout54776eab工作树干净。独立重建文件保留，约9GiB可用内存、57GiB可用磁盘。临时清单已登记，无清理、无上传权重/生成数据/被拒源码日志。

## 已完成的独立数值参考
0.8B L3采用明确的新M128 hidden及已验真实权重，生成完整Q[128,4096]、K/V[128,512]，671088640次顺序FP32 FMA，最后BF16 RNE。12个选定输出各完整1024步用Fraction复核末值，另4项顺序/tiny/非法输入/RNE测试通过。不是全输出独立比对，不是硬件通过，也不替代原hidden回归。
Q BF16 SHA30393d0d3bdcf9a9c576a1e8413a63c854b043795a10b6af3e6aec9e7ede4283；K b16025d546db17f698e2d097b544235d06da90806e887bc25e4e7fa42bf8a830；V f9072e9379f383edd47a44873ec9d1da1bfcd85c948aeaa14eb1b7848d4ef17a。
Qwen2此前新生成的21项/22输出文件重新校验长度和SHA均一致；这次只读检查不算新的编码或模型执行。

## 原硬件依赖
复用已编译原类，实际生成原FMA Pre/Mul/Post/Round四模块与HardFloat依赖，SV58373B SHAe372ab2c8f1308392b190409a75ae9090da27b4d1fc83bdc512bb0922d7963a0。没有生成Host SV，也未用缩小硬件冒完整4096。
历史107断言身份仍缺，当前105条源到lower逐项一致不代表历史等价。不能凭计数补造或删断言。真实Matrix/8ICG/1iDMA的17实例联合执行与完整数值资格必须另验。

## 后续与未解决项
优先真实Matrix原endpoint×8及17联合clock/reset/ready/native严格绑定；保留所有原异常约束，不把协议边界测试冒数值/fatal资格。35B L0/L3完整权重仍缺，未绕下载拒绝。32lane每周期共享向量及流水Div、跨tile缓存仍是待实现候选；本轮无完整block性能提升结论。

## Qwen2全Dense数学flags新增验证
原身份40256 exit0，154.45秒完成七Dense共5989466112个递增K步，2949120输出逐word一致；exact5225100787、NX764365325，无UF/OF/NV/DZ。31个FP64非零残差被TwoSum统计，本轮未新增“naive漏NX”实际独立见证，不能如此宣称。
另20处49971200转换词检查数学NX/UF/OF，并通过96边界和4溢出拒绝测试；无实际数学UF/OF。计数是唯一物化词集合，不是动态硬件转换事件。保持原FP32累加、乘数BF16_RNE及两RMS原物化位置，不把acc每步改BF16。此范围不包括真实硬件flags接线、完整所有算子异常聚合或全输出Fraction穷举。

## 17绑定审计
静态计划已记录8Matrix+8ICG+1iDMA的真实实例路径、端口、ABI及gated clock/reset条件。仍缺Host105条strict callback重建、17路联合稳定边沿动态测试、真实fatal注入与完整savable状态闭包。四个允许源码包查无历史107清单/IR，此阻塞未解决。

## 真实Matrix和17库共存有界验证
原编译19899及后续58014均exit0。新libmatrix SHA28abf8792ca3b0576568a0ef308efced8c7dfccf5778eaf24900068a08b908a5；单原endpoint direct-vs-CABI共400 halfcycle/208400输出word一致，200rise/199fall、单K输出及回执各1。
同时创建8个相同512MAC endpoint，整体固定4096，分别A=1..8/B=1，4096结果全部正确，8未eval析构通过。没有以单512替换整体4096硬件资格。
同进程同时装载8Matrix+8真实ICG+1真实iDMA，共400 halfcycle/reset/清理有界验证通过。此处是17native并存及边界，不是Host互连调度、完整prefill、故障注入或严格fatal通过。原endpoint内部mflags不直接通过其接口导出，仅protocol_error，因此不能用本次ABI通过声称Host全部算术异常覆盖。后续须沿原接口和异常契约补齐联合资格，不能放宽fatal。
