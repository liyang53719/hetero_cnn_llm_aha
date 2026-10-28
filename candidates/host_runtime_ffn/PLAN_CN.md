# TEMP：真实 Dense FFN → Residual2 staging

从 `host_runtime_postnorm` 的真实 FFN-input receipt 继续，同一 Commands/Guard/Kernel/Top，不另建调度器。**实际一次增量 Scala 类型编译：7 源 /950 baseline →51 新类；最终30源151类 =23继承源100类 +7新编译源51类，并非30源重编。** native exit0，空日志，55.685秒，前后各3464严格pin一致。

## 接线与资格

仅 profiles1/2、H1024/F3584：真实 postNorm→Dense gate/up→原 SiLU×up→Dense down→Residual2。profile1沿M16/M128，profile2沿M128，cold generation0。原 MATRIX/POLICY v3 op2 role4/5/6及 PROGRAM/POLICY v3 op9 role1/2仍由原 Record128/TypedTensorReader验证。五phase私有标记为gate1/up2/SiLU3/down4/Residual2 5，0保留旧路径。

Prefix的五项固定receipt账本只来自真实 Guard physicalDone.fire；gate/up核postNorm、SiLU核gate/up、down核SiLU、Residual2核Residual1/down。完整Host/transaction64/typed allocation、logical/physical job、严格非sentinel P<C、不可重放、实际ACK、MAC或专用Elementwise服务计数/drain全部绑定。Commands先验证原done并保留proof，仅原completion.fire且proof不变/无fault才发布下一stage。readonly预置、同shape/epoch不能代替生产者。

故障撤销资格，不撤回已公开held payload、不退款或伪造drain。原adapter/Guard继续拥有实际retirement；未知返回、Core/transport/service poison仍可能需joint isolation/reset，不承诺无条件有限排空。Residual2仍只是staging；profiles1..4 launch seal、cache/state最终双根fence均封闭。

## 数值和固定硬件

复用已有 TransposedDenseDownOwner/Matrix、同一runtime Elementwise owner、Scalar8/Format9。Dense保持原FP32累加、升序K与down的2560+1024 chunk/prefix次序、原BF16输出。SiLU为exp(-abs(g))→denominator→inverse→sign乘→乘原gate→**BF16(SiLU)**→乘up→**BF16(output)**，每元素6 Scalar/2 Format；不能先BF16(sigmoid)。原<=−80 Unsupported/error、Add和Attention SigmoidMul算术/运输保持。

M128合同（不是DUT实测）：每次gate/up/down usefulMAC469762048，总计1409286144；每份权重7340032 bytes。SiLU Scalar2752512/Format917504、64B memory43008、ACK917504B；Residual2 Scalar/Format各131072、memory12288、ACK262144B。

同三组32元素BF16缓冲1536 bits及value/exponential64 bits，**1600 numeric bits未新增**；Enum6→7仍3bits。kind9/stage77、Scalar8配额2621440→2752512，Format9配额1048576不变。private job新增phase3bits+public21Reduction1bit，内部job及快照ABI增长4bits，外部Host844bits不变；五stage/fullHost/txn/source/pending/comparator/mux等另有非零控制面积，未给综合面积数。

原4096MAC、32 SRAM banks/786432B、共享32-lane算术bank及FPU/formatter/DMA不增。Down要求原region3至少524288B且与A/W/D整段不交叠，这是既有外部DDR scratch要求，不是新增SRAM；源码复用不等于物理资源/时序证明。

## 保留并修复的真实缺陷

- 旧Public21 Router用physical tag低16==1/4/7猜语义；Guard持久物理sequence使hetero碰撞及后续Qwen2 launch不安全。现在仅原Commands验证后的official profile0/public21 Dense pc1/4/7生成私有语义bit，Router不再用physicaltag选路。原shape拒绝、K1024+512、pairReverse、FP32 storage及held/debt主体保持；不是Host注入授权或从shape推断。
- 独审发现初版Prefix结构资格读取fault-masked `authority.postnormCommitValid`形成组合反馈，已改为注册物理proof及保留job；实际fire/发布另行veto live fault。这是源码修复，尚未elaborate，不宣称全Top无组合环。
- 原独立GDN是layer0/M1、Attention是layer3/M1；不冒充任意layer/M128。原Qwen2 resident H1536/F8960与当前0.8B不是切profile即可互换。
- 35B profiles3/4 MoE的expert IDs、tie policy、router/allocator/expert/shared/merge调度均未改；arbitrary groupRows1..128对当前production Dense M16/M128的限制仍未关闭，不能宣称全MoE执行验收。

## 复核与未完成门

`SOURCE_PINS.json`列7新源、17公开继承、6 requires-parent；前代961+39=1000，移除7完整SourceFile族50类→950；**950=(855−旧RMS3−旧Router2)+100=850+100**。前代148类减48→继承100。新Router整族此次真实重编。

Router可读重建源与记录source92身份一致、当前baseline两旧类可核；**原历史209 compiler receipt不可用、未重查**，没有伪造可读路径或补写历史PASS。`SOURCE_PROVENANCE.json`明确此边界。旧历史missing/budget-skipped诊断仍是历史记录，不是本批新扫描；active输入闭包PASS不代表全档案图PASS。

`REPRODUCTION.json`仅精确argv占位配方/caps；需父级完整source/build/class闭包、106 jars、314-file JDK和原严格有界supervisor。无二进制/模型payload，不宣称fresh-checkout完整复现，也不是新启动授权。

普通Python与`-O`下通过81当前功能模型：Commands29、Prefix20、Elementwise17、Router15，及源码/负控检查。历史90模型包含9个准备前提检查，其中actual不存在只在编译前成立；不把后验重跑称PASS。独立源码review的36合同/7突变及重跑作者模型不是额外DUT数值样本；注入相同Exp的有限图比较不是硬件polynomial或Torch bit-exact证明。另有实际class/source/pin独审和精确receipt/closure/source绑定。保存owned-cleanup proof由原runner当时验证，后审不重观察已结束handle，不声称raw scans仍保存。

从包目录运行（外部两份原源码必须匹配`SOURCE_PINS.json`，相邻`host_runtime_output`与`host_runtime_postnorm`保持）：

```sh
python -B verify_package.py
python -B check_commands_ffn.py
python -B check_ffn_prefix.py
python -B check_ffn_elementwise.py --original-elementwise-source /path/to/original/GdnElementwiseOwner.scala
python -B check_public21_semantic_route.py --original-router-source /path/to/original/Public21QkvReductionRouter.scala
python -B tests/test_commands_ffn.py
python -B tests/test_ffn_prefix_contract.py
python -B tests/test_ffn_elementwise.py --original-elementwise-source /path/to/original/GdnElementwiseOwner.scala
python -B tests/test_public21_semantic_route.py --original-router-source /path/to/original/Public21QkvReductionRouter.scala
```

将`python -B`换为`python -B -O`复核优化模式。**无Chisel elaboration/RTL/DUT/数值协议仿真/QoR，完整五profile M128与同RTL验收仍0/5。** 下一门是解决MoE真实执行/资源合同及最终HostACK双根fence，再做同一Top初始化/位宽/组合环/物理实例资源及协议数值DUT，不以此TEMP候选替代。
