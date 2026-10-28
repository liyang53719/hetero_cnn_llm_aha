# TEMP：runtime QKNorm 与 Commands held-offer 最小修复 r2

**真实common mode10 / kind6-stage74 / Scalar8接线；仅源码和类型编译证据。r1编译PASS但协议源码FAIL，r2只重编1份Commands。完整五profile M128/RTL仍0/5。**

## 实际链与支持边界

原typed Dense Q/K/V→同一Guard真实physical job/done及完整Host/txn64/epoch/role/ACK→Prefix依赖→Kernel runtime QKNorm→同一Scalar8和memory client1→真实norm/gate写ACK→Commands staging。
profile2 Q8/H1024与profile4 Q16/H2048使用同一安装，不打开旧legacy Attention flags。Q投影每head是Q256+gate256，K/V宽512；Q先K后、全QKV真实完成、完整allocation/fresh/disjoint与later owner/replay均检查。

**共同parent的Dense链仍只支持M16/M128。** QKNorm leaf本身1..128容量、局部parser或geometry的M1测试不等于common链支持1..128，更不等于整块可启动。profile2/4 launch seal保持关闭。

QKNorm authority6/stage74只借Scalar8，cap2,695,168，不借Format9/Vector10、不扩大Norm/GatedNorm cap。C1每token/head1290 Scalar，C2为1316；原r3 op/a/b、ROM、完整switch、lane次序及本地整数BF16 RNE归一化逐字保留，实际captured flags语义保持。没有新formatter/FPU/Matrix/DMA。

请求/返回/精确accepted-returned计数、held payload与不可变terminal保留；未知tag/policy/out-of-wait返回隔离不退债，late fault只排已有债。Q16/M128/C2合同2,695,168 Scalar、65,544 memory ACK、2,097,152写ACK字节；这些是预期合同，不是实测DUT次数/周期或torch数值证明。

## 必须保留的失败发现

r1真实24源类型编译成功之后，补充审查发现旧Commands在`state===issue && resident.resetRequired`调用fail。若runtime job.valid已经暴露而Guard.ready为0，下一拍state改变，未握手offer被撤回：**source Decoupled稳定性协议源码FAIL**。先前独审漏检；compilerPASS不能代替这个协议边界。

这个反例发生在source job.fire前，不代表已接受物理债被抹掉或退还。问题早于QKNorm，旧runtime Norm/Dense/Conv/RawPrep/Chunk/GatedNorm同样受影响；所有旧批仍只是TEMP/类型证据，不是本边界协议验收。原源/日志/失败发现不覆盖。

r2唯一可执行改动是该guard增加`!boundRuntimePrefix`（另改说明注释）。完整bound/job.valid保持，Guard currentFault仍挡新接受，phaseResidentFault/moePhasePoison/resetRequired不变；等待既有joint reset/隔离，不制造完成、不抹债、不批准单独本地reset。legacy profile0行为不改。
`R1_TO_R2.patch`为脱敏差异，`check_held_fix.py`逆变换验证r1完整hash。

## 两次实际编译，不能混称

|阶段|实际编译源|基线classes|新classes|证据范围|
|---|---:|---:|---:|---|
|r1|24|855|108 /3,846,614B|compilerPASS；source-offer协议FAIL|
|r2|**1**|**959=855+104**|**4 /991,352B**|仅fresh Commands增量编译|

最终24源class闭包=23个未变源继承r1的104类+r2实际4类，共108类/3,846,678B；逐类hash/internal name/SourceFile无重复或基线shadow。**不是24源在r2重新编译。**
r1 wall56.217s/CPU47.92s/peakRSS605,933,568B，每轮pre/post1460pins；r2 wall33.074s/CPU27.46s/peakRSS409,874,432B，每轮1562pins。两次exit0、空log、owned组终态。发布不再启动编译器。

normal/-O历史源6763/18mutations，公开版另核2个前批源pin；Commands3985/12mutations/24geometry，owner18、integration20、held8小测试。另有982项旧QwenOwnerJob初始化/ABI静态审计的hash绑定。它们均不是elaboration、RTL、DUT或数值验收。

## 资源实账与未完成项

新QK owner固定payload **16,896 bits**（4×256×16+16×32），另 **288 bits** workregs、计数/terminal/完整Host+txn/provenance/held metadata；QwenOwnerJob增加8-bit policy。Commands不扩producer表、不新增算术module，不能称零总面积。保持hub17、adapter11、同32-lane bank与原4096 Matrix定义；实际实例/面积待同一Top elaboration/综合。

PartialRoPE→KVAppend→GQA→O→residual→postNorm→FFN/MoE→最终ACK/双根fence仍未闭合。Q16 GQA计数须实际按`2*M*C*heads*256`处理，不能沿用旧Q8固定移位。本批只完成QKNorm，未声称完整Attention或后继已做完。
下一门是同一真实Top的位宽/初始化/IO/组合环/资源，再完成实际后继链，然后同一DUT/RTL公共DDR路径M16再M128。参考模型只能外部比较，不回灌成功或结果。

## 小检查与requires-parent

```sh
python -B verify_package.py
python -B check_source.py
python -B check_commands.py
python -B check_held_fix.py
python -B tests/test_qknorm_owner.py --original-source "$EXACT_R3_OWNER"
python -B tests/test_qknorm_integration.py
python -B tests/test_held_commands.py
# 同样使用 python -B -O 重跑
```

本包7份最终源码、11份pin绑定公共sibling、6份历史编译源。原r3 owner仅用于18个来源/模型测试，须外部提供并hash验证。r1历史Commands不重复上传；若需要r1手动配方，供给完整pin匹配原件或逆patch恢复。
`REPRODUCTION.json`有**两个独立历史命令模板**；855/959的class source/build closure、JDK314文件及bounded supervisor未随包，仍requires-parent，不是fresh-checkout完整复现，也不是新运行许可。
不提交权重/NPZ、class/JAR、IR/SV、ELF或文本编码二进制。只交源码、pin/hash、中文计划和小检查；旧失败/历史原件不清理、不改写，不手动触发CI。
