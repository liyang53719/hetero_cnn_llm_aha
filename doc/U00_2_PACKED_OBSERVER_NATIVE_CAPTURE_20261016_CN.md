# U00.2 Packed Attention 观测适配与实际 M1/M2 小验证

## 结果与边界

2026-10-16，独立审查后的 packed 观测适配器完成实际 native M1/M2 小验证，正常退出，1.731938369秒，20秒预算不变。输入是现有确定性合成Q/K/V fixture，不是官方模型hidden state或官方13权重载荷。

使用原始精确类 `OfficialAttentionOwner`、`ProfiledMatrixService`、`ScalarService`，没有替代实际owner或算术服务。独立原始Fraction oracle的最终输出和因果score检查通过；观测到的PV与真实已ACK写回输出相符。十项字段都完整捕获，但其余八项仅获得实际捕获/覆盖证据，不能据此宣布与独立数值reference一致。

- M1：1768个owner/parent模型边沿，128次DDR读、96次写，完整捕获12个因果score/probability、192个dot stripe、36个normalizer word、1536个PV word。
- M2（带backpressure）：4857个owner/parent模型边沿，256次DDR读、192次写，完整捕获36个因果score/probability、576个dot stripe、72个normalizer word、3072个PV word。
- 上述边沿/FMA数是软件或native模型计数，不能当作RTL周期、物理资源或有用墙钟MAC利用率。

## 观测合同

新适配器保留原有十项数值字段、字布局、causal presence mask及未来位置sentinel。packed概率每个因果key只产生一次观测，normalizer每个head/query只观测一次；明确记录这与legacy八个PV列组重复捕获的差异，不虚构八次采样。

inline dot BF16与pre-BF16 probability只读取实际源绑定scalar return事件，不重算数值补齐中间量。漏捕、重复、未来key、错误scalar顺序、线程/回调篡改、终态前异常或任何未清空的scratch/output debt都会拒绝完整观测。

生产调用明确要求正常CPython3.12，`-O`在构造器即拒绝，不能静默关闭捕获。29个正常冷测试通过；优化模式19个通过、10个live-monitor测试明确跳过，并另有明确拒绝优化生产调用的测试。证据归档9个正常及9个优化冷测试通过。

## Git源身份故障与修复

第一次小验证在0.374秒、owner job开始前失败。真实ScalarService通过 `git show HEAD:chisel/continuous_prefill/tests/qwen2_block.cpp` 核对已提交算术；仅复制文件的composition缺少Git上下文。该失败保留，没有继承PASS。

经诊断和单独批准的一次重试使用真实独立be00 Git checkout，再覆盖完全相同的184个已审查文件；原始committed C++与工作树相等。没有伪造Git metadata或stub source_identity。原始已完成的be00 M128失败工作区未改动。

- Git HEAD：`be00eb8e4bc75e2e41f2a434d05d4c901ed3faa5`
- 184源manifest：`92268dce7c2ab0a65168a75219191a405891b2d4d2e0b61d919900a4d43c927c`
- 观测pins：`10f4c2fcaafe9be96298049611c86307ebff54787a2490b6bbe62e9b01153a8f`
- 实际安全capture：`98c8709956a1e47574aeb7e67316e8f3312bce69f9c1b4445daac99b4671f799`
- 原始committed C++：`d757e1271210e260ca320cddf4175c306d3cf52835ea45f20ca9dfb56ac34db5`

归档位于 `candidates/qwen2_resident_matrix/attention_packed_observation_evidence/`，只有safe receipt投影、大小/hash、计数/shape、冷测试及解释，不含权重、数值数组、ELF或私有日志。冷验证证明记录完整性与源身份，不是独立外部认证或重新执行。

## 计划/检查清单

- [x] 单独冻结packed观测适配器，保留十项字段/causal mask，明确packed multiplicity。
- [x] 独立审查与合成M1/M2/M16覆盖测试；实际M1/M2十字段捕获、ACK输出及独立score/output检查。
- [x] 保留首次pre-owner Git身份失败及经审查的一次修复重试。
- [ ] 真实M16资产独立来源复用、fresh arena及双reference生产，经冻结launcher和独立审查后单独执行。
- [ ] 链接原始完整Public M16 entry，严格combined ELF、晚读取reference、原始阈值和所有gate；先审查，后申请整链路运行。
- [ ] 全Public、full29、官方输入数值、RTL、实际资源和MAC利用率验收仍未通过。
- [ ] 最终目标仍为Qwen2-1.5B、Qwen3.5-0.8B、Qwen3.5-35B-A3B典型block，固定batch1/M128与实际RTL有用墙钟MAC利用率90%；M1/M2/M16中间验证不降低目标。
