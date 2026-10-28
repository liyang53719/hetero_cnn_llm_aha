# TEMP：真实 Chunk → GatedNorm 共享服务接续

**真实 Commands→同一 Guard→Kernel mode6→memory client1 的源码接线，23真实源 Scala compiler-plugin 类型编译成功。不是 RTL/DUT/数值或整块成功。五profile完整M128/RTL仍0/5。**

## 实际接续

- 同一typed三record `0x20→0x21→0x23`增加op5，仍五tensor槽。A必须是已真实完成Chunk的BF16 typed staging，B为实际Z projection，gamma为FP32[128]；slot3读gamma、slot4必须sentinel。完整allocation/region/live/fresh及operand、descriptor互斥检查。
- Chunk只在真实Collection done.fire、full accepted、Guard tag/status/写ACK/精确returned counts/drain匹配时保留terminal快照，等Scalar8/Vector10实际retire后才可供后继。
- Prefix在实际logical.fire保留Host/txn/job/Chunk快照；physical.fire再核G>C、epoch/txn/input/head/token并拒绝重用旧收据。来源失败但物理job已接受时仍保留ownership并poison，不假退债。
- 新authority **kind5/stage73**借同一 **Scalar8/Format9**。Kernel mode6实例化一个runtime GatedNorm owner并排除旧GatedNorm实例，复用原共享Scalar/format与memory client1，保留parentFault/reset/drain/held-job路径。
- 最后输出写ACK后才可成功；真实doneFire的完整accepted/bytes/cycles及两个returned计数再次匹配才退租。修正了held `done.valid&&!ready`不应因`doneFire=false`被误判的问题。Commands仅发布staged GatedNorm tensor，不提交最终双根/generation。

## 数值来源与资源账

旧owner的FP32 scalar op/a/b映射去空白逐字相同：128平方、128升序加法、mean/epsilon/sqrt/inverse及后续normalize/weight/exp/activate/gated次序不改。两次BF16 RNE边界仍由原bank policy4处理raw FP32；无本地先round再送bank的double-round，也无新增formatter。这不是torch bit-equality或已验证数值精度。

每head预期1284 Scalar、256 format、12 memory ACK，每job另8次gamma读取。M128/H32预期5,259,264 Scalar、1,048,576 format、49,160 memory ACK、1,048,576输出字节；**这些是源码成功合同，不是实测次数或周期**。format每请求仅lane0有效，其他31物理lane为+0，不宣称32有效结果/拍。

新增owner工作payload **10,240 bits**（gamma128×32加core/gate/output各128×16），Commands两个DecodedTensor **798 bits**，另有计数、状态、terminal及provenance/held元数据。不是零payload、零面积；不冒充综合总寄存器数。
保持adapter Count11、hub17逻辑客户、唯一32-lane bank、原DMA与4096 MatrixMAC定义，不新增hub client或算术bank。资源、时序与实例计数仍待同一真实Top elaboration/RTL核验。

## 本批证据

- 10份改/新源码，7份已发布公共源码逐字复用，6份历史编译输入仍requires-parent；无stub。
- 唯一一次本批实际编译：23源、855不变baseline、101新classes /3,577,669 B；exit0、空log、无baseline同名shadow。56.913s wall、48.20s sampled CPU、575,631,360B peak RSS；preflight/postflight **每轮1,431** pins。发布阶段不再次编译。
- normal/-O：6,688项源/词法检查与12错误接线变异；Commands54项与10变异；Python小合同15项。这些不是6,688个数值case，也不是DUT仿真。
- source/evidence/command/class身份hash由独立只读审查复核。历史manifest/checker的“未编译”scope是当时记录，本次实际成功另见ACTUAL_FACTS/EVIDENCE_PINS；不修改或重写旧失败证据。

## 未完成与下一验收门

Host profile1/3 launch seal仍关闭。后续O投影、residual1、postNorm、profile1 denseFFN、profile3 MoE完整数值链及最终双根fence仍未闭合；局部GatedNorm staging不是full block。
Attention **kind6/stage74只预留，未在本批实现**，不能借用GatedNorm或Norm authority域，也不能宣称Attention已通过。
未运行Chisel elaboration、宽度/初始化/组合环完整检查、CHIRRTL/RTL、native协议/故障DUT、官方数值M16/M128或QoR。旧leaf仿真、参考模型、源码合同和本次compiler PASS不替代这些验收。

下一步先在相应资源/许可门满足时验证同一真实Top elaboration；再沿实际typed producer与ACK接O→residual→postNorm→FFN/MoE→最终fence，最后同一DUT经公共descriptor/DDR跑M16再M128。不得用假ACK、外部参考回灌、放开opcode或绕开seal冒充完整执行。

## 可重跑的小检查与requires-parent

```sh
python -B verify_package.py
python -B check_commands.py
python -B -O check_commands.py
python -B tests/test_gated_contract.py
python -B -O tests/test_gated_contract.py
python -B check_source.py --parent-source-dir "$EXACT_ORIGINALS"
python -B -O check_source.py --parent-source-dir "$EXACT_ORIGINALS"
```

`SOURCE_PINS.json`区分10本包、7公共sibling与6未附编译源，以及21份原版本源检查输入。855类source/build closure、完整314文件JDK及bounded supervisor未随包；`REPRODUCTION.json`为原23源命令精确逆映射手动模板，**不是完整fresh-checkout复现、可执行supervisor或新的运行授权**。
只交源码、pin/hash、中文计划及小模型测试；权重、NPZ、class/JAR、IR/SV、ELF及任何文本编码二进制不进入Git。依赖/数据仅本地或CI按需恢复；不清理原件、不手动触发CI。
