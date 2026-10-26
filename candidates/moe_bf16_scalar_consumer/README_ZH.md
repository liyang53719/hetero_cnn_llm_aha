# MoE BF16 scalar consumer r2 — TEMP / CPU120 FAIL

这是待集成共享源码，不是35B完整block或完整4096硬件PASS。consumer固定32个BF16 lane，通过外部原ScalarRequest服务完成MulIeeeRne→BF16物化→Add→BF16物化，自身不实例化ALU；test-only wrapper连接现有一个HardFloat scalar和固定16槽MoE顺序控制器。完整top与实际matrix/expert投影并未接入。

分层事实：原r1有3个事务源审阻断；r2修复原子8/9 admission、当前唯一身份credit、真实producer.done&&protocolError的drained失败收敛。独审通过只意味着测试准入。28源fresh编译EXIT0。一次原5test执行在CPU120.04秒触帽被结束，outer1/child-9；严格retained-leader双扫描清理通过，前后源/jars/classes/Golden无漂移。整个suite未通过，首spec也未完成，后4case未执行。

唯一部分数值实证：txn100完整9贡献×32lane，576个真实shared-scalar请求/返回，numeric while-loop2020cycles。所有实际Mul/Add操作数、所有32lane最终BF16结果和身份/背压/消费断言后才打印checkpoint。它精确匹配随包官方eager全synthetic小Golden；不是完整MoE矩阵、真实模型权重、M128或完整4096性能结果。原日志没有第二笔逐周期记录，也没有保存逐op raw trace，不能猜终止时阶段或声称txn101功能失败。预算FAIL不会被此部分结果覆盖。

fixtures/official_eager_tile.json是已实际使用的原字节13KB合成fixture，所有参数先清零再设置少数明确常数，没有checkpoint或用户输入。FIXTURE_ORIGIN列官方4类method-body pins与确定性构造；可选expert backend decorator未执行，使用原eager函数体。原runtime、真实权重、classes、IR、大SV、原log、机器路径和PID均不在此包。

REPRODUCTION为角色化复现说明，不是新的运行授权。SOURCE_PINS引用已有106-jar清单、28源和固定strict cleanup helper。监督模板只把机器根替换为显式角色，原执行源SHA单独保留，不能冒模板原字节曾执行。重放需要重新校验所有依赖并用新输出目录，须单独预算批准；当前FAIL证据不可覆写。后继观测或较大预算验证完全不混在本包。

NaN/Inf/overflow（包括有限FP32 midpoint物化BF16 Inf）仍是已知未支持合法BF16范围，不能以小有限样例冒官方全数值语义。取消/超时依赖父watchdog隔离并真实drain；错误结果零payload为无效数据，不得发布为计算输出。
