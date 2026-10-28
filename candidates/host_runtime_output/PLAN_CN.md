# TEMP：实际输出尾 Gate → 原Dense O → Residual1，最终fence仍关闭

**Attention2/4真实QKNorm opaque gate ACK+真实GQA context ACK → 原sigmoid/BF16/context乘/BF16 → 原Dense O → Residual1；GDN1/3真实GatedNorm → 同一个Dense O → Residual1已接线。仅源码独审、有限模型与实际7源类型编译通过；完整五profile M128/同一RTL仍0/5，不打开最终launch seal或cache/state双根fence。**

## 原数值路径和准入范围

Attention gate保持`exp(-abs(g))`→`1+e`→`1/denom`→符号乘法→**BF16(sigmoid)**→乘context→**BF16(output)**。每元素恰好5 Scalar+2 formatter；不是SiLU、不插GDN RMS、不改变FP32节点顺序。负gate≤−80继续Unsupported，不捏造exp下溢或UF/NX标志。Residual1为原FP32 Add→BF16，每元素1 Scalar+1 formatter。原Qwen2 FP32存储分支保持。

新leaf只支持Add0/SigmoidMul2，不宣称FFN SiLU、Residual2、postNorm或MoE已实现。Attention输出尾只M128；GDN仍M16/M128。cold、generation0、精确shape、完整allocation相同、权重readonly、目的fresh/disjoint和来源角色均受约束；leaf范围不能当整个公共链范围。

Gate必须绑定真实QKNorm双输出ACK及GQA完成快照；O只能使用真实Attention SigmoidMul或GDN GatedNorm ACK的stage。Residual A是实际inputNorm job.a，不是norm/postNorm结果，B为真正O ACK。Guard logical/physical fire、child done和Dense physicalDone、完整Host/txn64/epoch、accepted全字段、全32位严格P<C/非sentinel/反重放共同核验，不接受预置readonly lookalike替代producer。

Commands只在实际done/精确tag-status-writeBytes以及completion.fire+currentFault veto后记录gate/O/residual staging，未发布最终根。Prefix没有新增独立的Residual→postNorm physical receipt；postNorm仍依赖既有真实Commands残差完成及原full-context Guard。本批不声称postNorm/FFN/MoE/最终fence闭环。

## 同一资源与诚实的故障恢复边界

common Top固定实例化一次runtime Elementwise，复用原owner kind13/Kernel mode9，mode14仍Chunk。新authority kind9/stage77只借原Scalar8/Format9，独立caps2621440/1048576，前代全局4-bit authority域不再加宽，不授Vector10。

固定BF16 buffer是**三个32元素×16-bit，共1536bits小计**；另value/exponential各32bit中间寄存器，数值存储合计**1600bits**，不是再增加三个共享32-bank算术硬件。还另有FSM、held child job、publication observers、真实债/ACK计数、terminal及Host/txn/producer快照均非零面积。使用原hub17/client1、DMA、共享formatter、32lane数值bank及同一个4096-MAC Matrix/Dense；原Qwen2 transposed/seed/packed/reduction mux保持。实际实例/RAM/面积/时序/五profile同RTL hash仍待elaboration和综合，源码计数不是物理证明。

修复并保留三项运输协议源码发现：
1. mode9 child job新增真实held保持，latefault不能撤回已公开未接受job。
2. leaf resetRequired不再直接反映local faultNow，打断job.fire→bounds fail→resetRequired→Kernel admission→job.fire反馈；local fault注册进poison，独立currentFault仍立即生效。
3. adapter已真正接受但尚未送Core的Scalar sOffer是实际债。仅active mode9的registered sOffer可绕过**leaf gdnPoison**，Core/physical fault、quarantine、冲突、legacy debt等检查全保留；不能授权新的raw请求或扩张至其他mode。

另修hetero Dense的PC碰撞：runtimeDenseProjection/runtimeDenseO排除Qwen2 `materializeDenseOutput`，Prefix O同时拒绝该位；legacy profile0分支不改。

**原Dense没有新增abort接口。** 已接受Dense遇晚fault仍按原物理transport/ACK语义执行，poison阻止成功stage/final发布；不能宣称全部新请求立即停止或无条件有限排空。service自身poison之前已公开未接受的held请求、未知回复可能必须joint isolation/reset，不能撤回offer、退款或伪造drain。现mode9修复不自动认证继承mode13 GQA的faultNow admission模式，该模式在本次leaf独审中明确未修改/未认证；统一Top组合环/协议DUT仍是未关闭门。

源码review是**两个独立分域报告的作者合并**，不是第三位独立reviewer的新审查；公共投影另做独立安全与证据复核。历史QKNorm协议FAIL、KV legacy kind7修复、GQA两P1及preflight失败记录继续保留。

## 一次真实编译，不能称28源全部重编

|范围|源数|classes|
|---|---:|---:|
|本次实际编译|7|49 /2,772,173B|
|未变继承|21|92|
|最终闭包|28|141 /4,877,414B|

947 baseline=855历史祖先+92保留类，亦为前批989−六个完整替换SourceFile类族42。实际SourceFile/internal-name/SHA、源身份/继承和无shadow核验通过。原legacy Elementwise7类仍在baseline，不混称runtime V15重编结果。

exit0，wall60.865s、CPU49.92s、peakRSS549,662,720B、tree18,384,152B；pre/post各3205pins，129条symlink_target保持，空log。frozen runner运行时执行owned cleanup验证；后续审计核对保存proof的身份/时序/scans摘要，不重跑已结束handle，也不声称保存了raw scans。

preparation首轮独审曾把classpath里的firtool-resolver.jar误认为firtool执行，后用实际compiler argv消除该误报；原review log保留，**不是本批真实compiler失败**。本批没有第二次compiler。原prepared材料保留其历史状态。

## 小检查、资源合同与复现缺口

历史74模型=Commands21+Prefix22+Elementwise25+preparation6，normal/-O当时通过。**公开当前功能模型是68，不含那6个precompile前提测试**；其中“actual目录不存在”在编译完成后不再成立，不能将现在的重跑伪报PASS。Commands历史4230/22mutations，公开版另核1个外部Guard pin；Prefix77/26mutations，Elementwise15源码变异。模型注入相同确定性exp替代primitive，只比较图和BF16 materialization位置，**不运行原ExpNegative degree7服务，也不声称Torch/native-bit数值相同**。

M128合同（非实测）：Attention gate在2048/4096宽分别1310720/2621440 Scalar、524288/1048576 format、24576/49152 memory、524288/1048576写ACK bytes；Dense O为268435456/1073741824 useful MAC；Residual H1024/2048分别131072/262144 Scalar与format、12288/24576 memory、262144/524288写ACK bytes。无性能提升/QoR承诺。

```sh
python -B verify_package.py
python -B check_commands_output.py --guard-source "$EXACT_GUARD"
python -B check_output_prefix.py
python -B check_arithmetic_delta.py
python -B tests/test_elementwise_review.py --original-source "$EXACT_ELEMENTWISE" --core-source "$EXACT_CORE"
python -B tests/test_output_prefix.py
python -B tests/test_commands_output.py
# 以上同样使用 python -B -O 重跑
```

原Elementwise、Core Qwen2Block、Guard必须外部提供并核完整pin；无私有路径默认。Commands检查删去两个结果写文件动作，算术差异脚本删去--write入口，原脚本hash留证。原始历史precompile tests只给digest，不伪装成现在可运行的资格测试。

本包7新源、15公共sibling、6 requires-parent历史源。REPRODUCTION提供实际7源手工argv逆映射，但947类source/build closure、106 jars、314文件JDK及原strict bounded supervisor未随包；**requires-parent，不是fresh-checkout完整复现，也不是新运行许可**。active输入/继承source-class精确不等于完整历史JSON图PASS；前批519未解析/899预算跳过是历史诊断，本批未声称重新扫清，`historical_transitive_graph_verified=false`。

下一门仍是同一Top IO/初始化/位宽/组合环/资源和真实数值/协议DUT，再接postNorm/FFN/MoE及最终ACK/双根fence。外部参考仅比较，不回灌成功。不上传权重/NPZ、class/JAR、IR/SV/ELF或编码二进制；不清理历史，不再编译或手动触发CI。
