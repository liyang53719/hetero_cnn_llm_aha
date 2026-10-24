# Qwen3.5-0.8B L0：内部 InputPrep token 外循环提案

状态：SOURCE PROPOSAL，尚未独审、未执行 Scala/RTL/模型。本候选不改当前正在运行的 Qwen2 全块，不继承任何旧 PASS 或 actual 权限。

## 1. 精确基底与改动范围

Remote main 固定锚（由 root 的 GitHub read API 核实）：`adefaa78c2d313d9927b4e87550dddc926b3c605`。

唯一拟改生产源：`chisel/continuous_prefill/src/main/scala/heteronpu/continuous/GdnInputPrepOwner.scala`，原 13,048 B，SHA256 `86fa350cd87bc140b762db2deb5650c25e3b30bae4fb12cef7fe407e6b4faffe`。保留原文件，只在本独立目录保存 overlay 与统一 diff。

新增构造参数 `maxTokens: Int = 1`，范围 1..128。默认值 1 保持所有原 public 实例只接 M1；本批不改 QwenOwnerProtocol、HostBlockCommands、descriptor、recurrent owner 或其拒门。仅显式选择 maxTokens>1 的内部独立实例可接受多 token，并限定 heads=16；原 M1 小 heads 测试域不变。Job/result/port Bundle 不新增字段。

## 2. 明确 packed 布局与检查

M1：保留原分离的 queryIn/keyIn/valueIn 和 query/key/value/gates 指针能力、旧 span/overlap 逻辑及 recurrentMode 两种算术路径。

M>1：必须 `recurrentMode=false`。官方仅“已有 state 且 seq_len==1”选择 recurrent；carried M128 仍是 chunk，不能把 !cold 当多 token recurrentMode。

每 token 的固定布局（heads=16，width=128）：

- Conv BF16 一行 12,288 B：Q 在 0，K 在 4,096，V 在 8,192；各 4,096 B。
- AB BF16 一行 64 B：A0..15 后接 B0..15，每 token 必须重新读取。
- Prep FP32 一行 25,600 B：Q 在 0，K 在 8,192，V 在 16,384，gates 在 24,576；gates 每 head 64 B，仅 g/beta 两字，余 56 B 全零。
- ALog 为原 FP32，dtBias 为原 BF16；均仍读取一个合法 64 B beat，每 token 重读，不混入参数缓存优化。

多 token admission 先核指针精确相等关系：keyIn=queryIn+4096，valueIn=queryIn+8192；key=query+8192，value=query+16384，gates=query+24576。使用宽位加法或在宽位完整 span 上界门后比较，禁止 64 位 wrap 被当成合法关系。

随后核完整 allocation：读 Conv [queryIn, queryIn+M*12288)、AB [ab, ab+M*64)、ALog [aLog,aLog+64)、dtBias [dtBias,dtBias+64)；写 Prep [query,query+M*25600)。每个 base 必须 64 B 对齐、完整末端不超过 2^56，Prep 不得与任何读区重叠。读区彼此重叠规则保持旧契约，不新增无依据的排斥。禁止用“各角色旧单 span 乘 M”代替 packed allocation 检查，因为跨 token 的角色包络会相交。

实际地址：Conv role 指针 + token*12288 + head*256 + beat*64；Prep role 指针 + token*25600 + head*512 + beat*64；gate 指针 + token*25600 + head*64；AB + token*64。ALog/dtBias 不加 token 偏移。边界 token=127 的所有访问必须仍在同一已核 allocation 内。

## 3. 控制与算术不变项

复用原 13 状态和 16 operation；原 scalar opcode、操作数、FP32 rounding、Q/K 升精度与 reduction 顺序、epsilon/sqrt/div、Q scale、beta BF16 RNE、g 的 exp/softplus 路径、数值拒门全部保留。没有新增算术单元或 DMA，没有并行 token，不改变 Head→Role→Beat/Lane 的既有内序。

新增 token 寄存器在 job.fire 清零。仅在当前 token 最后 head 的 gate 写响应被匹配 tag、确认无 error 并 ACK 后，若还未到最后 token，则推进 token，重置 param/head/role/beat/lane 与必要局部累加器，并转 readParam。每个 token 仍先读原 AB/ALog/dtBias 三个参数 beat。sequence、bytes、cycles 跨 token 累积，不能每 token 清零。最后 token 最后 gate ACK 后才出成功 terminal；done backpressure、错误 finish→locked 与联合 reset 约束保留。

M1 token 恒为 0，因此旧地址和算术/握手轨迹不变。M128 成功预期输出 ACK 总量=128*25,600=3,276,800 B；这不是总 fullblock 输出或利用率分母。

## 4. 本批轻量检查与资格边界

仅目标 CPython 3.12.14 的纯源码/合成控制，禁止 Scala 编译、RTL 生成、native、模型构造、权重/张量读取或实际后四 block。检查包括：

1. 精确 base/source pins，diff 只落上述构造/地址/范围/token 转移点；原算术块和握手失败分支逐字核对。
2. M1 分离指针退化等价；M=2/16/128 的首末地址、每个 token/head/role/beat 唯一覆盖，AB 刷新和输出完整性；这些是地址合同合成，不宣称运行 Scala。
3. 错 role offset、跨 token alias、末端 2^56 溢出、不对齐、M0/M129、M>maxTokens、多 token recurrentMode=true 的负例；默认实例仍拒 M2。
4. token 边界必须等待最后 gate ACK；stall 不提前推进，tag/error 不推进成功，最后 gate 未 ACK 不成功；源码转移检查与合成计数分列，不能把替身当真实硬件握手。
5. 后续真实 owner/RTL 资格另需原 scalar request/result 与 memory request/response fire trace、完整中间 Q/K/V/g/beta、stall/错误/terminal 粘滞、M1 回归与跨 token 哨兵检查；本批不执行。

顺序 token 化只扩内部 prep 功能域，调度仍串行，吞吐及共享 Scalar 利用率未证明。不得称 chunk64、完整 prefill、public Command128 或 RTL 已实现，更不能以局部 prep 的分母宣称全块 80%/90% 利用率。真正 chunk64 的三角系统、state 更新和固定资源映射仍是另一份源码/算术/调度工作。
