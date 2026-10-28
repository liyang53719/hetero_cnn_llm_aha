# TEMP：实际 runtime PartialRoPE，共用 Scalar8 的增量类型证据

**QKNorm真实ACK → 原Commands/同一Guard/Prefix → common mode11 → 原Scalar8/原memory client1 → RoPE真实写ACK已接线。仅源码与真实Scala类型编译通过；未做elaboration/RTL/DUT/数值验收。完整五profile M128/RTL仍各0/5，profile2/4 launch seal关闭。**

## 实际链与支持范围

原0x34/PROGRAM→ATTENTION→AUX parser显式B1；真正Q/K norm typed allocation及成功ACK齐备后，Q先K后。Prefix producer绑定完整Host、txn64（不截高32位）、epoch、role、shape、输入、严格producer<consumer及逐role反重放；不用Host成功标志或仅地址/几何相等代替物理完成。真实physicalDone.fire与child accepted/returned/写ACK快照齐备才能retire lease；Commands真实completion.fire且currentFault veto通过才发布rotated typed tensor，保留gate staging，不开放cache/history/state/final可见根。

同一common Top固定安装Q16/K2/M128容量，Q8/Q16只是运行配置。mode11 / kind7 / stage75仅借原Scalar8，独立cap393216、192次/token/head；不借Format9/Vector10，不扩大QKNorm/Norm/GatedNorm等cap。原hub17、memory client1、adapter11、同DMA/Matrix/32lane bank保留，QwenOwnerJob ABI不加宽。

**共同Dense parent仍只支持M16/M128；本次Commands仍是cold全窗、base0/count=M、generation0、position0、无cache。** leaf的1..128 token和较宽合法position范围不等于common链支持这些配置，更不等于整块可启动。

## 数值顺序、故障与历史缺陷

原PartialRope64Owner的operand/op/a/b与完整switch归一化逐字比较：每pair依次mulEc、mulOs、mulEs、mulOc、sumEven、sumOdd，4次独立FP32乘法+2次独立加法，每次真正返回均经原整数BF16 RNE转换再扩宽。rotate64、余192 BF16按位搬运；无FMA、重结合、近似或改图。原Math helper来自923基线，历史compiled-source及真实class身份见LEGACY_CONVERTER_PIN；**未重编该helper，也不是数值DUT证明。**

held首次公开/已公开区分，latefault不撤回offer，匹配返回才退已接受债；未知tag/policy/out-of-wait返回不fire、不退债。未知隔离后可排后续精确已接受回复，但sticky unknown不声称resourcesDrained，仍需既有joint reset/transport isolation；terminal在背压/latefault下保持，父链故障veto不变。

继承QKNorm r2的`!boundRuntimePrefix` resident guard保持。前批r1真实24源编译PASS但后来发现source-offer协议FAIL，r2仅1源修复；旧Norm/Dense/Conv/RawPrep/Chunk/GatedNorm同缺陷及先前审查漏检历史不改写。反例在job.fire前，不是已接受物理债抹除证据。详见已发布sibling `../host_runtime_qknorm/PROTOCOL_DEFECT_AND_FIX.json`；旧批仍TEMP，不借本批宣称已完成协议DUT验收。

## 一次实际增量编译，不能称25源全量

|范围|源数|class数|
|---|---:|---:|
|本次实际编译|7|47 /2,381,152B|
|未变继承|18|68|
|最终闭包|25|115 /4,033,934B|

923 baseline =855历史祖先+68保留类，也等于前批963−六个完整替换SourceFile类族40。实际7源覆盖、逐类hash/internal name/SourceFile、无shadow和继承来源已核验；**不是25源重新编译。**
本次exit0，wall47.297s、CPU39.78s、peakRSS509,882,368B、tree17,540,647B，每轮pre/post1582pins、空log，owned进程组终态。发布不再次启动编译器。历史prepared文档保留，其“尚未编译”是当时状态，不覆盖当前真实receipt。

小检查normal/-O：owner45源码项/18mutations/17模型；Commands3997项/14mutations/12geometry及18模型+8继承held；arith17795项/14mutations；integration历史6707项/47mutations/25模型，公开版另加1个祖先pin检查；独审34断言。它们不是elaboration、协议DUT或数值验收。

## 资源实账和下一门

新owner固定数值payload **6208bits**：trig2×512+input8×512+outputs2×32×16+products4×16，另FSM、计数、terminal、held及Prefix完整Host/txn/producer寄存器。不是零面积。没有新增FPU/formatter/DMA/Matrix/银行；原4096 MAC定义保留，真实实例/RAM/面积/时序及跨profile同一RTL hash仍须同一Top elaboration/综合，当前无RTL hash证据。

M128合同（非实测）：Q16为393216 Scalar、33024 memory、1048576写ACK bytes；Q8为196608/16640/524288；K2为49152/4352/131072。

下一门：同一Top初始化/IO/位宽/组合环/资源审计；完成KVAppend→GQA→O→residual→postNorm→FFN/MoE→最终ACK/双根fence。Q16 GQA按`2*M*C*heads*256`核MAC，不能套旧Q8固定移位。随后同一DUT/RTL公共DDR链M16再M128。参考仅外部比较，不回灌结果/成功。

## 复核与requires-parent

```sh
python -B verify_package.py
python -B check_integration.py
python -B check_commands.py
python -B tests/test_arithmetic_authority.py
python -B tests/test_rope_owner.py --original-source "$EXACT_ORIGINAL_ROPE_OWNER"
python -B tests/test_rope_integration.py
python -B tests/test_commands_rope.py
python -B tests/test_commands_held.py
# 以上同样使用 python -B -O 重跑
```

本包7源码，12个既有公共sibling和6个历史源身份由SOURCE_PINS绑定。owner模型需外部提供精确原PartialRope64Owner并核hash。REPRODUCTION为历史7源编译手工argv模板，原923类的source/build closure、106 jars、314文件JDK和bounded supervisor未随包；**requires-parent，不是fresh-checkout完整复现，也不是新运行许可**。只交源码/小脚本/pin/hash/摘要；不交权重、NPZ、class/JAR、IR/SV/ELF或编码二进制。不清理或覆盖历史原件，不手动触发CI。
