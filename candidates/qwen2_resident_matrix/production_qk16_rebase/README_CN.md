# 默认关闭的production QK16源码重基

状态：SOURCE_ONLY_REBASE，未classcompile、未elaborate、未RTL/数值/EDA执行。仅把已有packed QK16控制重基到原production完整policy顶层；没有sixhead重排、packedPV、raw scratch、panel或新lease。原逐head softmax/PV正文逐字节保持。利用率80/90未验收。

## 精确输入与可复核组合

SOURCE_PINS固定5个production源码（含端口定义）与2个QK16 donor。production基底来自freeze d2772173/source；消费者使用自己的显式根，未依赖作者绝对路径。

python -B build_source.py --production-source /path/to/production --qk16-source /path/to/pinned/qk16 --output /path/to/new/output
python -B test_rebase.py --production-source /path/to/production --qk16-source /path/to/pinned/qk16 -v
python -B -O test_rebase.py --production-source /path/to/production --qk16-source /path/to/pinned/qk16 -v

output必须不存在；先核全部pins及唯一anchor，才创建5个修改/新增源码文件。输出不是完整工程，必须置于同一已钉production源闭包才能讨论classcompile。production_qk16.patch以production为基底零fuzz产生相同5个postimage，POSTIMAGE_PINS固定结果。overlay/与overlay_v2/是开发中旧输出，均不可安装；overlay_v3/为当前查看用postimage，发行仅recipe/patch/pins与冷测试。

## 逐文件改动

1. Qwen2Block.scala：追加enableProductionPackedQk16=false。启用要求ownerDriven、externalMatrix、完整OfficialBf16V2，原checkShape(capacity1024)不改。route只替换QK feed/gather/select，复用denseWeights256和acc16，无新payload阵列。仅选中Attention ownerJob在原Bounds链拒绝m>128；m0及其他bounds继承原检查。命令可fire后产生原错误terminal，但进入begin及任何工作请求之前拒绝，不能靠ready永久拉低。
2. 完整numericPolicy保留：生产已有materialize(dot)→scale→materialize(score)，原样单份；不引入旧partial official开关/helper。只在packed路径补materialized dot/score finite检查。旧softmax/PV与其他official RMS/RoPE/FFN逻辑不改。
3. 复用PackedAttentionStreamClient原字节：八depth步、一个context0、最终结果保持、匹配done/completion、abort排空逻辑沿用。QK16 capacity限制改为运行时activeM≤128的生产集成契约；token/key原UInt16不缩，packed count≤16。client仍pv=false。
4. MatrixPipeline.scala只追加默认关闭packedStepsDrained输出：work且metadata无头、无step offer、无poison。原transpose/seed/credit/队列/leaf路径不覆盖；该状态不是cycle预测。
5. QwenOwnerProtocol.scala：保留TransposedDenseDownOwner/resident/原SFU/Public21路由。packed mux在原非bf16AttentionCore的else内，useDense词法作用域正确。只有core packedOwned期间选择，断言active/mode0/!useDense。group逐字段接tag/opcode/sliceMask，transposedDense=false/groupSequence=0；禁止seed begin/beat/ack新握手。保留原五债务tracker正文，仍观察最终service真实fire。
6. Public21 reduction最后的abort override保留，新增reductionOwns与packedOwned不可同时的断言。不能把断言当已验证的动态互斥；真实top协议验证待办。
7. HostBlockTop/Collection只传播同一默认关闭选项到原owner，不新增顶层、不替换Commands或DMA、不删原production构造参数。其他作业M限制不变。

## 两个重基反例与修复

- 原useDense是else内局部，旧mux若插在else外将无法编译；当前放入同一else尾、五债务tracker之前，冷测检查词法brace范围。
- production matrixFault原用fmDone&&legacy.error，但packed覆盖fmDone后会误读未选中legacy stale error。当前改为matrixResult.fire&&matrixResult.bits.error；默认off原fmDone即该fire，packed错误只走原client reset/error及selected finite链。

## 债务与拒绝边界

core result.valid追加!packedBusy&&!packedFeedDebt，防止client已退休而DDR/local/scalar仍有接受债务时发布owner done。matching memory tag后才退memory债务；poison阻止新offer并维持已有响应消费。原core result→ordinaryDone→原Host fault链保留。默认off表达式退化为原路径，但尚未做elaboration/RTL等价。

冷测13项normal/-O：精确postimages、零fuzz patch同结果、policy/capacity保留、0/1/127/128/129/65535选择性Bounds、禁止预截断、原softmax/PV字节不变、5debt正文不变、seed逐字段、原client逐字节、无新payload数组、scope反例、stale-error反例及Matrix default-off源码投影。它们是源码/整数检查，不是握手执行；不证明held/stray/abort所有动态组合。

## 源级增量账本

core新增packedOwned/finalIssued/committed共3bit、tag32、memory/local/scalar债务3、gather4、selected4，共46bit；原client descriptor41+index8+poison1+8态FSM3，共53bit，合计99bit控制寄存器声明。原core state固定7bit追加两个编码，不扩大宽度。Matrix状态输出不新增寄存器。此为源码清单，不是综合资源报告。

无新增payload数组声明，但denseWeights256个FP32词现在被QK读取，若原选定production综合会裁剪这些词，可能重新活跃最多8192bit；不能称物理零成本。新增mux/索引/比较/路由也有逻辑成本，实际retention/area/timing待验证。

## 不混入的后续工作

sixhead调度、6max保存或重扫、score打包scratch ACK、inverse的ScalarDiv ACK、panel/V gather及48输出ACK退休属于后续独立片。当前不需要384B panel别名，不创建悬空guard-only Host开关，也不宣称已有真实packedPV供数。先独审此QK-only生产patch，再由root决定有界classcompile；没有自行执行编译授权。
