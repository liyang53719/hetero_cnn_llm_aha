# TEMP：实际 runtime KVAppend，双plane ACK只形成私有proposal

**K RoPE真实ACK + V Dense真实ACK → 原Commands/同一Guard/Prefix → common mode12 → 原hub client1/DMA → 双plane写ACK proposal已接线。仅源码和实际Scala增量类型编译通过；没有elaboration/RTL/DUT/数值验收。完整五profile M128/RTL仍各0/5，profile2/4 launch seal关闭。**

## 实际路径和边界

原0x41命令、0x24 v2 policy /0x26 v2 context及typed tensor parser，同一QwenOwnerJob ABI（n512/k256）。Common Top无profile条件地安装一个固定K2/D256/capacity128 runtime owner；Q8/Q16通过运行配置和真实producer变化，不制造Host成功包。

K producer来自真正K RoPE terminal.fire，V producer来自真正Dense physical terminal.fire；保留完整Host（含epoch/regions/profile）、txn64及物理producer序号。logical接受检查地址/shape/role/ACK，physical接受再逐包核对K/V各自严格P<C、全32位、allones拒绝及两producer replay。故障撤销可用性但不抹债；Guard原fullHost/txn64/no-wrap物理序列保持。

Top只允许读K/V输入、写各plane的[start,start+M)尾部，full64 mask、2^56 aperture及已接受region权限保持；owner检查**完整cache分配**与两输入pairwise disjoint，不只检查实际写尾。K先V后，每beat readInput→writeTail，512-bit BF16 payload按位搬运，无浮点运算/变换。

只有匹配且成功的真实write ACK计数；每plane M×1024B、总写M×2048B，memory accepted=returned=M×64，两plane齐备且真drained才生成proposal。Kernel/Prefix交叉核对完整accepted job、tag/status/bytes/cycles/counters、length=M/generation1。M128合同为8192 memory请求/返回、K/V各131072写ACK bytes、总262144B；**这些不是DUT测量。**

Commands仅保存private pending cache snapshot，不能把含未写行的整cache标成produced-live tensor；完整capacity仍防alias。Prefix receipt只供后继链，**不发布cache/state根、length或generation**。还须GQA→O→residual→postNorm→FFN/MoE→最终真实ACK/双根fence，本批不开放GQA。

**当前只支持实现层面的cold position0/length0/generation0、whole-window base0/count=M、固定cap128。共同Dense前置链仍限M16/M128；leaf1..128不是公共链全shape支持。** 无warm append/历史恢复承诺，profile2/4仍不可启动完整block。

## 故障修复与保留的历史

- 本批precompile审查曾发现无条件kind7拦截会破坏原Qwen2 legacy FP32 append。最终Kernel/Prefix只把kind7且activation/weight/output三个BF16标志全真送mode12；legacy仍core mode0。P1在最终source pin前修复，无waiver；HISTORICAL_FINDINGS记录，DUT跨profile路由验收尚未做。
- 原leaf wrong-tag直接finish行为已硬化：未知return不fire、不退真实债；sticky quarantine不能假报drained。后续精确匹配债可排完，但未知污染仍须既有joint transport reset。latefault不能撤回已公开held request，未公开意图可取消；terminal背压/latefault下不变，父级current fault仍veto发布。
- QKNorm r2 `!boundRuntimePrefix` resident-held修复保持。前批r1 compilerPASS但source-offer协议FAIL、旧runtime prefix候选同缺陷和先前漏检历史不覆盖；见既有QKNorm的PROTOCOL_DEFECT_AND_FIX。该旧反例在job.fire前，不是已接受物理债抹除证据。源码修复/模型不等于协议DUT资格。

## 一次实际5源编译，最终26源闭包

|范围|源数|classes|
|---|---:|---:|
|本次实际编译|5|37 /2,215,576B|
|未变继承|21|86|
|最终闭包|26|123 /4,203,268B|

941 baseline=855历史祖先+86保留类，亦为前批970类减四个完整替换SourceFile类族29。source SHA/class SHA/internal name/SourceFile/无shadow及继承身份已核验。**不是26源重新编译。** 原legacy KV、Guard及RoPE Math保持真实baseline来源，不宣称重编它们；INHERITED_HELPER_PINS绑定来源。

实际exit0，wall45.794s、CPU38.31s、peakRSS532,574,208B、tree17,709,757B，pre/post各1651pins一致、空log，owned compiler组终态。发布没有再运行编译器；历史prepared文档原样保留，其“尚未编译”只是当时状态。

normal/-O小检查：owner65项/19mutations/20模型；Commands4027项/17mutations，KV21+RoPE18+held8模型；integration历史6182项/53mutations/17模型，公开版另核1个祖先pin。模型覆盖每beat地址、M128 K-end=V-start合法相邻plane、opaque payload、完整cache alias、aperture、txn高位/fullHost变动、双producer顺序/replay、全部terminal evidence与暂存不发布；均不冒充Chisel/RTL执行。

## 资源实账和下一门

新增一个**512-bit payload寄存器**，另FSM、序列/accepted-returned/ACK计数、terminal、held、Prefix完整Host/txn/双producer及pending metadata；不是零面积。KV只用原hub17/client1，无Scalar/Format/Vector请求或lease，无新增arith authority kind，0..7/3-bit域不变。原adapter11、32lane bank、DMA、Matrix及4096MAC定义保留；实际实例、RAM、面积、时序和跨profile同一RTL hash仍须同一Top elaboration/综合，不拿源码计数代替。

下一门是同一Top初始化/IO/位宽/组合环/资源审查，并完成真正GQA和整block闭环；Q16 GQA按`2*M*C*heads*256`核MAC。随后同一DUT/RTL公共DDR链M16再M128；外部参考仅比较，不回灌结果/成功。

## 复核与requires-parent

```sh
python -B verify_package.py
python -B check_integration.py
python -B check_commands_kvappend.py
python -B tests/test_kvappend_owner.py --original-source "$EXACT_ORIGINAL_KV_OWNER"
python -B tests/test_kv_integration.py
python -B tests/test_commands_kvappend.py
python -B tests/test_commands_rope.py
python -B tests/test_commands_held.py
# 以上同样使用 python -B -O 重跑
```

本包5源码，15个已有公共sibling及6个历史源身份由SOURCE_PINS绑定；owner模型需外部提供精确Bf16KvAppendOwner并核hash。REPRODUCTION是历史5源手工argv模板；原941类source/build closure、106 jars、314文件JDK及bounded supervisor未随包。**requires-parent，不是fresh-checkout完整复现，也不是新运行许可。** 只交源码/小脚本/pin/hash/摘要，不交权重/NPZ、class/JAR、IR/SV/ELF或编码二进制；不清理/覆盖历史原件，不手动触发CI。
