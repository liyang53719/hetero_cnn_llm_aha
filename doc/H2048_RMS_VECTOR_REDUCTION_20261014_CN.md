# H2048 RMS 归约向量借用：同资源局部 RTL 实测

## 结论与范围

在相同冻结真实输入、同一组155个编译源、相同理想供数与末尾13拍 held done 下，M128完整RMS的 launch→done.fire 从 **1,792,902拍降到239,494拍**，周期比7.486208，下降86.642103%。两边均由生产core的实际Scalar计算inverse，输入与原始BF16 weight经DDR进入DUT，输出逐bit匹配原冻结观测。

主要资源口径包含本harness保留的全部33个HeteroFP32Alu：原elem16、legacy vector16及Scalar1。逻辑Add/Mul执行容量分数从 **2.252113%提升到16.859788%**，包含闲置legacy16的分母。原elem16子池单列为34.633018%。这些是调度执行容量分数；Scalar另有SFU能力，SFU等待不折算成Add/Mul，Matrix不在该harness库存内。不能称MAC利用率、全block利用率或物理吞吐。

本次仅是production-core-service局部RMS。useVectorReduction默认false，QwenOwnerKernel当前并未启用此归约候选；完整kernel command/Host链、目标DDR时序、综合后SRAM端口/面积/频率仍未验收。阶段预测最低80%/争取90%，最终实际完整RTL的90%联合目标不变。

## 复用资源和数值顺序

- 三块原32×512bit borrower bank，共6144B；四个FP32标量寄存器和完整19个owner寄存器声明均与对照相同。
- weight bank尚未装载gamma时，首128B暂存32个block partial；output首128B继续保存32个residue partial。inverse完成后按原流程装载weight，scratch不跨阶段占用。
- 原elem内五个512bit工作寄存器复用。fabric的两个512bit响应寄存器仍独立保留，不当作可借临时存储。原elem SRAM配置12288B保留，无新增ALU/bank/宽寄存器。
- CHIRRTL比较确认相同33个HeteroFP32Alu和memory声明；新增mux/control成本、实际宏推断和物理端口未测。

官方冻结recipe的8 lane×4 ILP归约树不变：每block显式+0后顺序累计16项；各residue顺序合并block0..3；各lane合并residue0..3；最终按lane0..7累加，所有原舍入点保留。

新SquareAccumulate loan先执行FP32 MulIeeeRne(x,x)，寄存该舍入结果，再执行严格FP32 Add(partial,square)，绝不FMA。128个此类loan和8个residue Add loan替代每token4224个Scalar节点，最终40个fold Add、mean/epsilon和Sqrt/Div仍走原Scalar。epilogue保持Qwen3.5的normalize Mul→Add(1+weight)→weighted Mul，不能套到Qwen2 direct gamma。

每token仍执行10410个逻辑Add/Mul节点：elem10368、Scalar42，另有2个SFU请求。事务为44 Scalar请求、264 loan、192个64B读、64个写ACK。全token串行，未借跨token重叠或新增上下文取得收益。

## 相同理想供数 A/B

| 规模 | Scalar归约 + 原vector epilogue | Vector归约 + 原vector epilogue | 周期比 | 全33配置执行容量：对照→候选 |
|---|---:|---:|---:|---:|
| M1 | 14021 | 1885 | 7.438196 | 2.249872% → 16.734989% |
| M16 | 224123 | 29947 | 7.483988 | 2.252010% → 16.854018% |
| M128 | 1792902 | 239494 | 7.486208 | 2.252113% → 16.859788% |

两边都取消相同测试器人工请求/返回延时，每DDR事务仍计request.fire和response.fire两拍，保留13拍held done和1拍terminal fire。没有把减少人工背压当成架构收益。目标DDR的延迟、带宽、冲突和并发配置尚未知，不能据此外推目标系统性能。

实测与模型逐拍一致：候选wall=1820×M+实际SFU pending+14，对照wall=13956×M+同一SFU pending+14；M1/M16/M128的SFU pending分别51/813/6520。每token恰少12136拍。模型中的SFU参数来自测量，不是独立SFU延迟预测。

全33分数=(elem有效Add/Mul lane-operations+Scalar普通ALU执行拍)/(33×wall)。M128分子在两模式都为1332480，分母分别59165766和7903302。候选elem有效Mul786432、Add540672，合1327104；Scalar执行5376拍，另有6520拍SFU等待。elem实际执行82944拍，service busy116736拍、reply驻留33792拍，后三者不能互换。

### M128互斥完整周期

| 区段 | Scalar归约对照 | Vector归约候选 |
|---|---:|---:|
| reduction服务，含计算/协议，不含DDR | 1645432 | 92024 |
| epilogue服务 | 81920 | 81920 |
| 全DDR请求及返回 | 65536 | 65536 |
| held done及终态fire | 14 | 14 |
| 总和 | 1792902 | 239494 |

候选还可互斥重分为：elem执行82944、loan请求/返回67584、DDR65536、Scalar尾部23416、terminal14。Scalar尾部为ALU5376+SFU pending6520+请求/返回及其他等待11520；与前表相加口径一致，不重复计入ALU。

因此后续理想条件的主要空档是loan协议和DDR供数，而不是原先占人工背压wall 82.67%的串行Scalar归约。这里仅提供瓶颈证据，尚未实施新的重叠流水或目标DDR优化。

## 额外人工背压正确性门

使用原周期性请求/返回保持和37拍末写ACK延时，实际M1/M16/M128全部逐bit通过，wall为4503/71150/568566。相应全33分数为7.005431%/7.093848%/7.101758%。M128互斥分桶为327707 DDR+128398 reduction服务+112447 epilogue服务+14终态。

此门单独记录，不能混入理想供数A/B。M128的elem执行仍为82944拍、有效lane操作1327104，额外等待只增wall，不增加执行分子。

## 数值、故障和来源证据

1. 首轮6项局部RTL门包含原loan回归、新两舍入primitive和资源门、真实core wrong-tag债务保持、accepted-write abort及不全局reset复用。新primitive实测最早3边沿退休、II4；1472个合成lane检查包括FMA反例、UF/NX政策、每lane/阶段异常、held reply、clear/abort、DDR优先与旧op复用。
   追加原默认fixed-bank owner、生产core、旧H1024 owner与Scalar epilogue对照4项回归全部通过，155源身份与数值配对相同；默认旧路径的故障/恢复门没有被候选替代。
2. M1配对先通过，再顺序运行M16/M128候选与对照；额外人工背压门随后完成。五份实际回执的155个源pin完全相同，fixture前后不变。M1/M16/M128 manifest分别为fdca7a3011740a44d1a1a26cc7570392b5fdb55993a849758829d4b71a205cc3、a0634202bcca950242d6e1c160be6897cd5e14e735b80936f625d0167850d6a0、799a8e3bc67c1dd32a77cc4766268a4d5c570639cf1fb7a18f87153fe008fde7。
3. 每次实际回放仅input/weight进DDR；11个expected文件只用于断言。RTL逐compound loan检查操作数和最终结果，并检查Scalar尾部和输出；未导出每个compound内部square的全部bit/flags。
4. 独立Python行为模型保留原整数FP32与有理数oracle，比较618280个semantic node，1236560次独立结果/flags检查；这个数字只属于模型。错误的升序sum在M1第0行恰好一致，却使M16的14行、M128的122行不同，因此M1不能单独证明归约树。
5. 模型源码从固定027d Git对象读取，当前owner改变也不刷新旧pin。portable脚本的冷模式明确不执行实际fixture或算术；只有完整fresh --run-actual才产生新的行为PASS。旧失败/早期包装回执保留，未继承其成功。
   最终portable脚本21项冷门在正常/-O均通过，最终源码fresh行为回放也完成618280节点。loan CI新增同样冷门和冻结Git源fetch；默认冷回执只标PASS_COLD_STRUCTURE_ONLY，外部实际算术明确NOT_EXECUTED，不继承本地行为或RTL PASS。

机器摘要：reports/execution/H2048_RMS_VECTOR_REDUCTION_20261014.json。原始日志、FIR和fixture留在ignored work，只提交源码、hash、计数和摘要。runner的generated_records仅是缓存目录库存，不能单靠它证明本轮生成归属。

## 复现入口

先source work/chisel_toolchain/env.sh，准备prepare_h2048_borrower_replay.py要求的冻结真实fixture。运行scripts/run_h2048_rms_borrower_tests.py，给定新的--out、--actual-fixture-root、--tokens和相应三个--mN-manifest-sha256。候选加--vector-reduction；对照不加；双方均加--ideal-supply才构成本文配对。省略--ideal-supply得到独立人工背压门。缺fixture或pin硬失败，不能算PASS。

模型入口scripts/check_h2048_reduction_order_model.py要求显式--root和新的--out；默认只做冷来源结构检查。真实行为复现额外给--fixture-root和--run-actual，外部根保存原历史runner/producer/manifest与payload相对路径。缺任一文件或身份不匹配就失败，无自动重建pin、下载权重或部分PASS。tests/test_h2048_reduction_order_model.py覆盖正常和-O的冷拒绝门。
