# TEMP：真实 Top / Kernel / Chunk dispatch 接线 r2

**实际控制/数据路径源码集成，20 真实源码的一次 r2 Scala 编译成功；不是硬件或完整数值签核。**
此前 r1 的真实编译失败完整保留。五 profile 完整 M128 Chisel/RTL **0/5**。

## 本次接入

原 Record128Reader / TypedTensorReader / Commands runtime op4 → 原 Guard 的实际 logical.fire / physical C.fire → 原 Kernel mode14 → 唯一 Collection 的五 leaf → 原共享 hub/iDMA、唯一 Core tagged Scalar、唯一32-lane bank。

- Commands 继续原五 typed slots / 三条有界 policy records / prefix 去重；A 必须是实际完成 RawPrep 的 typed tensor。M16/128、H16/32、完整区域权限及三写对象互斥检查；只作 output/stateOut staging，不发布 scratch，也不更新持久 generation/root。
- Top 在实际 logical.fire 保留 Host/txn/job/producer P receipt，再在实际 physical C.fire 验证 Guard 接受和 C>P 后提供一次性 held prepDone。保留原 P 标签；P=0 有效、all-ones 拒绝；late fault 不撤销已经公开的 offer，不能因上游 Valid 持续为真重复 offer。
- 真实 prepDone.fire 且 clean 后 acquire stage72 Scalar8/Vector10；精确 expected counts 来自 accepted M/H/策略。只有完整匹配真实 done.fire、full accepted job、status/bytes/count/drain 才退租；错包保持债务 quarantine。
- Scalar/Vector mux 在首次 publication 保留选择，在 request.fire 保存返回 owner，不按当前 valid 猜返回。五 memory 客户接同一 hub 的逻辑索引12..16；pending/tag 由真实火沿维护，回包必须匹配。
- fabricDrained 看真实 raw/held/pending/result 和服务债，不含 active owner/lease，避免等自己退租。故障挡住首次共享请求但仍计入 raw 未排空；held 请求可排空，fault 反射寄存避免明显回接组合环。此为源码结构意图，尚无 FIRRTL 组合环签核。

## 资源必须如实记账

- **hub clients12→17 是真实控制资源增长**：accepted/returned counters 增640 bits，owner 与 RR selector 各增1 bit，并增加组合选择。仍只有一个 hub、一个 outstanding、原 request/reply/transport sequence 存储。
- 保留共用4096 MAC、唯一32-lane V4 bank、原17个 Scalar 构造事实与唯一 Core tagged Scalar端口；不声称只有一个物理 Scalar、不声称新增 II1 吞吐。
- 新 helper 声明元数据4,039 bits，Kernel新增控制65 bits。Collection/五 leaf 现在实际进入共同 Kernel，**不能因原源码存在就说 Top 寄存器/控制成本为零**。这些不含全部新实例寄存器或组合逻辑，不是综合面积/PPA。
- H16 保留 legacy 数值路径，H32 用既有 guarded/finite-gradual；4份数值桥和3份 receipt/Collection/Coordinator 源码逐字不改。未新建数值 bank、算术 primitive 或 DMA；未以 profile 重新 elaboration。

## 成功与失败分别保留

- **r1 FAIL**：0338 原 compiler exit1，Bundle.binding 名称碰撞；0 qualified classes，26.141s wall、21.70s CPU，每轮1,412 pin checks。原失败 receipt/log 及源 manifest hash 保留在 `R1_FAILURE_AND_R2_FIX.json`。
- **r2 PASS，compiler-only**：仅 Protocol/Wiring/Kernel 各一行 binding→prepBinding；逆替换与 r1 逐字一致，没有协议/时序/资源语义改动。20 真实源 →95 classes /3,364,876 B，855 baseline，无同名 shadow；exit0、空日志。
- r2 每轮 pre/post1,413 pins；52.139s wall、44.34s sampled CPU、555,827,200B peak RSS。独立只读核验 source/class hashes 和真实 receipt；发布不再次编译。
- 冻结私有 source check normal/-O 各111项、12负变异；公开版另加14个公共源码pin检查。Python模型 normal/-O 各15测试，**不是 DUT 仿真**。

## 仍未完成

Host launch seal 对 profile1/3 仍关闭。后续 GatedNorm/O/residual、final 双根 fence/publication 及五 profile 整链未闭合，Chunk staging 不是完整 block 成功。
未运行 elaboration、CHIRRTL/RTL、宽度/初始化/组合环完整检查、native 协议/故障 DUT、数值 M16/M128 或 QoR。异常 held、unknown/stale、late fault 不自动撤销/reset，仍需实际 joint reset/transport 隔离。不能继承旧性能或数值资格。

## 复现边界与下一步

本目录只有7份新/改源码；另7份直接复用已发布 sibling 文件，具体 commit/path/hash 见 `SOURCE_PINS.json`；6份历史编译输入及18份原版本源码检查输入仍 requires-parent。
855类的 source/build closure、完整314文件JDK及 bounded supervisor 未随包；`REPRODUCTION.json` 是原20源命令精确逆映射的手动模板，**不是完整 fresh-checkout 复现、可执行 supervisor 或新运行授权**。

```sh
python -B verify_package.py
python -B tests/test_dispatch_contract.py
python -B -O tests/test_dispatch_contract.py
python -B check_source.py --parent-source-dir "$EXACT_ORIGINALS"
python -B -O check_source.py --parent-source-dir "$EXACT_ORIGINALS"
```

下一步先审查/验证真实 Chisel elaboration 的环、宽度、初始化与 held/fault/drain，再在相应许可和资源门下做 native 协议及数值检查；最后才推进 launch seal 与后继完整链。不要靠假 ACK、模型或局部编译代替硬件证据。
原件和历史失败不改；只发布源码、pin/hash、摘要及小模型测试，不提交权重、NPZ、class/JAR、IR/SV、ELF 或文本编码二进制，不手动触发CI。
