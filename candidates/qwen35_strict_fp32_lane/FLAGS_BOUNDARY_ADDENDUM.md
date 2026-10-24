# Tininess-after-rounding 边界与已有软件适配差异

本附录不改旧 vector16.cpp、旧模型、已封证据或原提案。它记录新审计发现，不能反推旧运行在该边界发生过错误。

实际共享 HardFloat RoundAnyRawFNToRecFN.scala:202–228 使用 unboundedRange_roundPosBit/roundIncr 参与 tininess-after 判据。输入a=0x00800000、b=0x3f7fffff，精确乘积为(2^24−1)×2^-150。该值可由无界指数24位精度精确表示，但小于minnormal；交付binary32落在maxsubnormal/minnormal中点，ties-to-even交付0x00800000且inexact。HardFloat源码应保UF，因此flags=3（UF|NX）。这只是对固定源码的静态推导，尚未新运行硬件。

原 vector16.cpp:49–50 重新按已交付fabs(r)<2^-126设置UF，因此此例会给flags=1。结果bits相同，但fatal mask30使错误资格不同。不得用旧CPP这个局部修正作为新lane全部flags的独立oracle，也不得宣称逐边界fatal资格等价。

官方SoftFloat FAQ说明tininess-after判定先按目标精度、无界指数舍入，不等于检测交付结果是否subnormal：
https://www.jhauser.us/arithmetic/SoftFloat-3/doc/SoftFloat-FAQ.html

新原型拟保原共享HardFloat的原始flags，不插入结果指数修补；该规范选择已提交root确认。软件独立Fraction参考应按无界指数24位RNE判tiny；其精确阈值是minnormal−2^-151，等于阈值时unbounded舍入到even minnormal，不tiny。

“接受subnormal/±0”只指无fatal flags的精确结果；最小subnormal×0.5虽交付零，UF|NX仍fatal。有限binary32 Add的精确和是2^-149整数倍，不能伪造一个自然tiny-inexact Add underflow例。

Reset有效周期压制request.ready/result.valid，避免清寄存器与外侧握手计数冲突。零pass拒绝只意味着不使能四级阶段寄存，不宣称零组合逻辑翻转。fatal pass诊断bits与flags仍置对应Valid，未执行字段始终零且Valid=false。

root 已在2026-10-21确认：本隔离prototype保原HardFloat flags继续；不改旧CPP/旧PASS，不声称与旧软件fatal30等价。此差异仍是未来集成数值契约阻断，原型通过也不会解除。

| 精确实数与RNE交付值 | 原HardFloat源码判据 | 旧CPP修正判据 |
|---|---|---|
| a=0x00800000，b=0x3f7fffff；精确乘积=(2^24−1)×2^-150；交付0x00800000且NX | 无界指数24位值仍tiny，unboundedRange_roundIncr=false，UF不因交付normal清除；预期flags=3，fatal30拒绝 | 交付fabs(r)==2^-126，不满足严格小于；修正UF为0；预期flags=1，fatal30不拒 |

表中两列均是对固定源码的推导，不是新硬件或C++实测。
