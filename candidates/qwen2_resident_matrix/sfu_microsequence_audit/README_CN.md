# 原 SFU 微序列与 divider 吞吐审计

结论：去掉 Add/Mul 的 request/done 空拍在功能上可行，但保持现有 16 个
options=0 divider 时，M128 的 90% MAC 利用率在数学上已经不可能。
71,680 个 SiLU vector 的正常除法独占这些 divider 至少 1,792,000 cycles；
即使把其余工作全部完美重叠，上限仍只有81.9455%。80%也只剩43,580 cycles
非重叠余量，现有按阶段串行的控制器远不能满足。这里没有运行 RTL、STA 或
算术等价验证，也没有修改任何实现默认参数。

## 可复现的 pinned 原始 divider

主工程 `chisel/continuous_prefill/scripts/prepare_hardfloat.sh` 锁定上游
`ucb-bar/berkeley-hardfloat` revision `c1105e6ac6a0dd90fc80893efc4830ab609005d3`。
本目录 `DivSqrtRecFN_small.scala` 是该 revision 的原文件，保留许可和版权。
其 Git blob SHA-1 为 `7f65d667a13a0cfb3b2bab15413cb5e71e176f2b`；测试通过
Git 的 `blob <bytecount>\0<payload>` 规则重算，不只信任文件名。
原文链接：
https://github.com/ucb-bar/berkeley-hardfloat/blob/c1105e6ac6a0dd90fc80893efc4830ab609005d3/hardfloat/src/main/scala/DivSqrtRecFN_small.scala

精确控制依据：

- 224–226行：cycleNum 初始0，inReady对应count≤1，rawOutValid对应count=1。
- 273–277行：normal division 仅排除任一输入的 zero/Inf/NaN。
- 300–319行：FP32正常除法入站置count=sigWidth+2=26；options=0 每拍减1；
  仅count=3且最高商位为1时跳过count2。**余数为0不是退出条件**。
- 390–399行：最高商位来自初始 trial remainder；不以余数是否归零改变计数。
- 495–515行：raw ready/valid直接透传，最后仍经原RoundRawFNToRecFN。

`counter.py` 逐边沿复刻这个 division-only 计数递推，不计算商或模拟FP32。
初次接受在edge0；最有利时edge25既消费旧结果又接受新输入，已经给足
same-edge return/reissue；非skip时edge26。没有另加 wrapper 空拍。
特殊输入可为1拍，但不能拿它替代成功 SiLU 的除法：
`VectorSilu.scala:43–50` 先exp(-abs(gate))，再FP32 1+exp，接着1/denominator；
`BlockFloat.scala:58–69,90–98` 拒绝非有限输入、使用原七阶Horner近似与>=80
的零截断。`exp_horner_interval()` 从源文件直接读取系数，用有理数精确模拟
FP32 nearest/even的区间端点舍入，保守包围fraction∈[0,1]的每个Horner节点，
验证最终区间下界>0、上界=1。最终再乘2^(-k)，k≥0，或cutoff选0，仍在[0,1]。
因此该成功路径的exp非负且≤1，denominator在[1,2]，两个除法输入
都是有限非零值。1/1、1/2的精确结果及零余数仍走normal并需要25拍；
1/1.5、1/(1+ulp)、1/nextDown(2)走26拍。任意实际trace应按源结果核查分母；
不能把“通常26”升级成所有输入都26。

## 同一 ALU 的逐拍算术可以怎样改

`integration/gemmini/EmitHeteroFP32Alu.scala:8–17` 内部 AddRecFN/MulRecFN
是组合连接，统一输出mux，round_near_even、tininess_afterRounding。
`BlockFloat.scala:90–98` 本来就在expMul/expAdd之间连续逐拍捕获依赖结果。
因此可以在同一16-lane SFU内新增默认关闭的微序列控制，让上一拍捕获的
FP32值驱动下一拍算术，避免每个primitive重复idle→normal→done。
这不是“算术延迟已达到1ns”：新mux、寄存器反馈、recoding、rounding和
fanout仍须STA；原源码仅说明800MHz是目标，不能宣称1GHz已闭合。

每个full exp仍有17个独立FP32/RNE节点：scale Mul1、fraction Add1、
七次Horner Mul+Add共14、finish Mul1；另有expFloor整型转换状态1。
保留现有转换边界时是18个状态，SiLU再加denominator Add及3个Mul，合计
22个非division状态；cutoff路径仍执行scale后选零，非division最低5个。
单上下文不能把dependent divider藏起来，最有利full SiLU仍约22+25=47个
服务周期/vector，尚不计输入/输出握手。仅更换外层FSM不会让这部分重叠。

数值/异常保护必须照搬，不可顺手改变：

- Add/Mul和Div原有invalid/div-by-zero/overflow、fatal-underflow、非有限检查
  见`BlockFloat.scala:71–88`；只有已有特殊opcode另有UF政策。
- exp内部primitive flags在原路径刻意忽略，不能因为逐节点接口而新增fatal
  flag；来源`ffn_attention/scalar_recipe.py:1–7,18–44`。
- `official_bf16/chisel_policy.patch:257–269` 在SiLU phase4及phase5插入BF16
  RNE/finite检查；不得改为只在最终写回舍入，也不得融合Mul/Add为FMA。
- divider返回为无ready的pulse，任何双上下文版本必须预留返回寄存器与tag；
  不允许因ALU忙或store stall遗失结果。失败仍要排空所有已接受请求。

## 资源、上下文与重叠约束

`VectorSilu.scala:34` 实例化16个BlockScalarFloat；每个包括一套ALU和一套
DivSqrtRecFN_small，当前参数是`BlockFloat.scala:49`的(8,24,0)。
这里HeteroFP32Alu已有add和mul组合电路，但只能通过已有一个输出mux选择；
不能在计数中把它当成两个独立输出服务。旧core另有16个vector ALU
（`Qwen2Block.scala:128–130`），是不同资源池，借用需单独路由/冲突账。

想重叠vector A的division与vector B的exp，至少要保存两组Gate/Up及exp/
denominator和一组不可反压的divider返回，并保持每组阶段/异常/tag。
源级可供评审的别名候选是：

- A的Gate/Up/exp：SiluVectorUnit input.gate/input.up/probability，192 B。
- B的Gate/Up/exp：VectorSiluOwner a/b及SiluVectorUnit value，192 B。
- 已预留divider返回及post-Mul accumulator：VectorSiluOwner output，64 B。
- exp的frac/horner/product继续使用BlockScalarFloat已有寄存器。

声明来源`VectorSilu.scala:29–32,91–94`、`BlockFloat.scala:40–41`。
这只是可审查的别名分配，当前FSM没有该读写路由；不得据此声称双上下文已实现。
output还承担最终store保持，必须先收到匹配ACK再回收；value必须等B的exp
已安全转移或作为B的exp上下文固定持有，不能被A的旧response路径覆盖。
如这些既有寄存器不能按时回收，就停发divider或明确增加并计账context，而非
用Python临时数组补齐。既有OverlappedSilu的输入2深/输出2深queue不能直接
移植为免费缓冲：tile-loan配置通过`ffn_tiles/tile_ports.patch:19–20,34`
明确要求non-overlapped owner。

现有FFN也没有Dense/SiLU同时运行：`ffn_group/model.py:159–194,250–287`
按Gate→Up→SiLU→Act drain串行，只有前一window全ACK才开始下一window。
`ffn_group/group.patch:424–454`互斥window busy、tile busy及SiLU loan；
`ffn_tiles/tile_ports.patch:286–356`只有3个tile槽、先seal全tile再read，
一个接受债务和逐列RMW。Dense A和tile虽word不重叠，仍共用相同16个bank的
read/write端口；允许compute重叠之前须有逐拍bank仲裁，不能同时免费访问。
可先研究同一个FFN owner的有界流水：前一批SiLU从已seal槽取数并捕获到上述
两帧，SFU计算期间Matrix使用下一批输入；复用已消费槽必须修改prefix valid/
release规则，并为Gate/Up/Act三类活跃数据证明存活区间。原3槽不是两套完整
ping-pong window，不能简单宣称“再处理下一窗口”已有容量与端口。

## 可选变更和必要预算

| 版本 | divider个数 | 算术/资源变化 | 正常输入最早重新接受 |
| --- | ---: | --- | ---: |
| 原options0 | 16 | 不变 | 25或26 cycles |
| 微序列+双上下文，options0 | 16 | 新控制/mux/可能context；除法递推不变 | 仍25或26 |
| 上游options16，默认关闭提案 | 16 | 每拍第二组trial/subtract/select逻辑 | 14 cycles |

上游`common.scala:65`定义divSqrtOpt_twoBitsPerCycle=16；本文件300、313、
371–399行实现第二组试减和两位更新。options16没有增加divider实例数量，但
增加组合逻辑、切换负载和关键路径，属于显式的新资源/时序配置。原舍入器、
RNE及异常接口未更换，这只说明应可保持同一数值合约；仍需用原参考门逐位比较，
包括special/subnormal/边界/异常、长stall和完整SiLU，不能当作等价已证明。
新增divider实例、共享reciprocal或近似reciprocal都不是本次实现：共享只在
逐位相同denominator且生命周期可证明时成立；换近似会改变现有参考，不建议
据此放宽门限。

M128 useful=6,014,828,544，固定4096MAC/cycle，80%总预算1,835,580，
90%预算1,631,626又2/3。原divider最优25×71,680=1,792,000，已排除90%。
若每个16-lane vector都出现26拍lane，division alone为1,863,680，上限78.79%；
这是有条件情形，不能当作通用26拍证明。

options16的divider服务降为1,003,520；但full-exp微序列ALU为
22×71,680=1,576,960，已经接近90%总预算，仅剩54,666给所有不重叠工作。
因此即使options16+双上下文，也不能保证90%。还须实际统计exp branch比例、
服务阶段和bank开销，推进合法FFN/Dense与可能的跨token流水。
在保留完整M128前置阶段屏障时，仅Q/K/V/O及packed Attention Matrix issues
就有243,840；加full-exp ALU1,576,960已达1,820,800，80%仅余14,780，
连82,944个scratch服务边沿都放不下。不同SFU/Vector池的合法分工也可评审，
但不能算成已存在的重叠。下一实现应是可配置的逐拍微序列和实际loan调度，
先验证数值与所有资源冲突；90%继续保持未验收。

验证：在既有pytest环境运行本目录，普通及python -O各12个测试。
覆盖源码Git blob、精确除法、normal/special分类、同边沿return/reissue、
options0/16递推及90%必要上限；没有执行硬件算术。
