# TEMP：runtime GQA mode13，真实共享Matrix/Scalar链与增量类型证据

**Q RoPE真实ACK + KVAppend双plane完整ACK → 原Commands/Guard/Prefix → common mode13 → 原Scalar8与同一个4096-MAC Matrix → 输出真实ACK链已接入。仅源码独审和实际7源类型编译通过；不是DUT数值或协议验收。完整五profile M128/同一RTL仍0/5，profile2/4 launch seal和最终cache/state根保持关闭。**

## 固定实现与实际支持范围

同一common Top固定Q8/Q16、KV2/D256 runtime owner。叶子MaxTokens128、score capacity256、MaxQueryHeads16；**当前实际Commands只cold M128/C128、cache capacity128、position0、pair-high-first（order1）**。leaf更宽几何范围不等于公共链已开放，不能沿前批M16/M128前缀支持推断本次GQA支持M16。

原r3六个数值区段逐字来源比较：Q/K/V地址和Matrix operand顺序、每score六Scalar操作scale/mask/difference/exp/sum/divide、FP32/BF16边界、mask Add、最终BF16选择均保持；不跳mask、不融合或近似。runtime r3原件SHA为d1dc6e17…；保留在baseline中的legacy GQA来自**另一份**d4c1047d…原件，不能把两者混称同一编译来源。SOURCE_PROVENANCE记录完整pin。

GQA复用原Matrix service及8×512=4096 MAC slices、Scalar8、hub17/client1和DMA。Qwen2 transposed/seed/packed/reduction旧完整路由保留，互斥与固定安装检查不替代RTL组合环/真实资源审计。没有新增Matrix/FPU/DMA/Scalar bank。

完整Host/txn64/epoch/accepted快照、Q和KV各自严格P<C及反重放绑定真实producer；Scalar实际接受/发出/返回、Memory ACK、Matrix group terminal/drain共同核验。三条融合completion按原顺序held，Commands只保存private GQA staging；**KV proposal和GQA输出暂存不是最终cache/state根发布或整block完成**。

## 真实资源变化，不能称零面积或接口不变

authorityKind全局**3→4位**，所有profile使用同一新定义；GQA独立kind8/stage76，只借Scalar8，cap3,145,728。旧kind0..7数值及各自cap保持，不把kind8截成MoE kind0或别名RoPE，不借Format9/Vector10。

宽度源码/旧class引用审计识别至少**23个retained authority寄存位增量**：adapter11、MoE8、Prefix2、Chunk2；还存在完整Host/producer/terminal/计数/publication observers等控制元数据。23只是识别到的authority字段，不是全部资源增量。共享接口身份确实改变，当前没有“旧接口hash不变”或五profile同一RTL hash证据。

GQA继承r3固定存储声明并实际安装：query8KiB、keys16KiB、scores16KiB、qk1KiB、output8KiB、value0.5KiB，合计**49.5KiB主要staging**；另maximum64B、scalarValue/sum/seen、FSM、债/计数/terminal和Prefix元数据。保留**32个本地terminal BF16 rounders**。这些不是新共享FPU bank，但不能省略或称总面积零；真实RAM推断/优化后寄存器/面积/时序仍待同一Top elaboration/综合。

## 已修复的问题与未关闭的验收

独审发现两个真实P1源码问题，最终7源已修复，历史finding不覆盖：
1. leaf把被外层故障门禁止公开的raw intent误记为held，可能阻止已接受Matrix债abort/drain。四条memory/Scalar/group/step改由**实际publication观察**提交held状态：未公开意图可停，已公开offer保持，不新增publication→raw-valid/reset组合反馈。
2. sticky parentFault每拍fail覆盖drain→finish。已经drain时不再覆盖状态；known debt可真正退完后产生失败terminal，idle fault直接锁定不伪造done。

未知身份/过早Matrix terminal仍quarantine，不能伪造drain，必须既有joint reset/transport isolation。上述是源码/抽象模型结论，DUT独立通道首次/held背压、持续fault、乱序/unknown以及组合环均未验收。

继承QKNorm r1 compilerPASS/protocolFAIL与r2 held resident修复，以及KV legacy kind7误截P1修复的历史。HISTORICAL_FINDINGS引用原公共记录，不把旧TEMP改称已获协议DUT资格。

logicalMAC改为66位中间量检查后的`2*M*C*Qheads*256`，Q16不再错误使用Q8 shift12。M128/C128合同：

|Q heads|Scalar|Memory beats|Matrix groups|写ACK bytes|useful MAC|
|---:|---:|---:|---:|---:|---:|
|8|786432|147456|320|524288|67108864|
|16|1572864|294912|640|1048576|134217728|

这是正确工作量计数，不是吞吐/周期测量或性能提升。

## 一次真实编译与首次preflight失败

首次0837 attempt在preflight被原严格校验器拒绝：active manifest归一化遗漏129条`symlink_target`。receipt owner/exit/log为null、RSS0，Java未启动。fresh0903 pinfix只从精确前代恢复该元数据，未改源码、校验语义、资源caps或实际symlink，原失败receipt保留。不是放宽验证重试，也不把未启动说成编译失败后源码修好。

|范围|源数|classes|
|---|---:|---:|
|0903实际编译|7|52 /2,684,253B|
|未变继承|20|82|
|最终闭包|27|134 /4,556,781B|

937 baseline=855历史祖先+82保留类，亦为前批978−六个完整替换SourceFile类族41。逐类hash/internal name/SourceFile、源身份和无shadow已核验。**不是27源全部重新编译。**
实际exit0、wall59.206s、CPU48.60s、peakRSS547,774,464B、tree18,063,513B；pre/post各3077pins、空log、owned compiler组终态。发布不再运行编译器。原prepared文档保留其历史状态，不覆盖当前receipt。

normal/-O：66新模型（owner28/Commands19/Prefix19）；owner45源码项/16mutations/65536几何；Commands4030/15mutations；Prefix53/21mutations；arith103574/16mutations；integration历史65121/7mutations/57344地址路由，公开版另核1个祖先pin。既有47 Commands抽象模型历史通过。它们不是Chisel/RTL执行或DUT数值等价。

## 复现边界必须真实

**active输入/源-class闭包精确PASS，不等于完整历史传递图PASS。** 广义archive诊断有519条缺失/未解析引用、899条预算跳过；历史JSON边界只固定文件身份，未递归证明全部祖先。旧迁移/失效引用没有被假路径或“继承PASS”掩盖。REPRODUCTION_LIMITS明确`historical_transitive_graph_verified=false`。

本包7实际源码、14公共sibling和6 requires-parent源身份。手工REPRODUCTION argv已逆映射到实际7源命令，但937类的完整source/build closure、106 jars、314文件JDK及其symlink元数据、原strict bounded supervisor未随包。**仍requires-parent，不是fresh-checkout自包含构建，也不是新运行许可。**

```sh
python -B verify_package.py
python -B check_integration_gqa.py
python -B check_commands_gqa.py
python -B check_gqa_prefix.py
python -B tests/test_gqa_arithmetic_authority.py
python -B tests/test_gqa_owner.py --original-source "$EXACT_R3_GQA_OWNER"
python -B tests/test_gqa_prefix.py
python -B tests/test_commands_gqa.py
# 以上同样使用 python -B -O 重跑
```

公开Commands检查移除原脚本的两个结果写文件副作用；arithmetic_delta只保留read-only预期差异函数，无写源码入口。原脚本证据hash保留。owner测试需外部精确r3原件并核hash；不提交旧bytecode或源码编码权重。

下一门：同一Top IO/初始化/位宽/组合环/真实资源，再接O/residual/postNorm/FFN或MoE和最终ACK/双根fence，最终同一DUT/RTL公共DDR验证。外部参考仅比较，不回灌成功。未做elaboration/RTL/数值/协议DUT/综合/QoR；不上传权重、NPZ、class/JAR、IR/SV/ELF或编码二进制，不清理历史、不手动触发CI。
