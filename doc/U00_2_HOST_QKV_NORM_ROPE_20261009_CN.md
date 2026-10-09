# 生产 Host 的 QKV、Norm256 与 partial64 RoPE 命令子链

本项是 C03.2/C04.2/C05、S01/Q35A 的局部接线子门。当前本地已通过 owner 数值与 Host 前端控制门禁；七命令生产 Host 数值仍 **PENDING**，不得用单元测试、构建或描述符 roundtrip 代替。U00.2 保持 ongoing，U01 保持 to do，C02.2 原官方完整精度门禁保持 OPEN。

## 实际接口与数据依赖

默认关闭的 `bf16QkNormRope` 依附现有 Qwen3.5 QKV profile。`EmitHostBf16QkNormRope` 仍生成生产 `HostBlockTop`，复用同一个 Dense owner、MatrixPipelineService、八个 Matrix512 物理 slice、原 iDMA 及 core 中的 Scalar 服务。Norm/RoPE owner 不实例化另一套 Matrix、Scalar 或 DMA。

一个窗口依次执行七个普通 Command128：Dense Q/gate、Dense K、Dense V、Q Norm、K Norm、Q RoPE、K RoPE。前三个保留公开投影 policy v2；后四个使用标准 RMSNorm 0x32 / RoPE 0x34、engine3、A/B/D 三根，后接显式版本1的 ATTENTION_POLICY 0x24 和 ATTENTION_AUX 0x25。Q gate 是独立 typed 输出根。内部 owner kind 扩至已有4位中的14/15，不复用旧语义。

固定几何为 hidden1024、Q/gate packed4096、Q context2048、K/V512、Q8头/K2头、head256。Q投影每头保持 `[query256, gate256]`。所有张量使用 BF16、连续元素 stride；描述符记录完整行数，active window 单独绑定。RoPE `positionBase` 是第一个 active token 的绝对位置，不再叠加 `tokenBase`。carried127 的绝对位置是255。

所有后继读数必须匹配实际完成并接受 completion 的指定 producer，readonly 预置的“同形状中间值”不能充当前驱。Q/K/V 的行数与 active window 必须一致。完整 allocation 参与跨命令 alias 检查；active 字节参与发布。每次 owner 的所有写 ACK 完成之后才允许成功结果，Q Norm 主输出和 gate 两个 span 一起发布。输出故障保留已写 staging 内容但不发布该命令。

单 token 有114条描述符、7条命令，实际写 ACK 应为24576B：Q8192、K1024、V1024、NormQ4096、gate4096、NormK1024、RoPEQ4096、RoPEK1024。M128 形状准入不等于 M128 数值执行。

## 算术保持原定义

Norm 复用 C1：16元素平方的平衡树归约，16个 chunk 顺序相加，FP32 均值与 epsilon1e-6，原 PWL32 ROM 加一次 Newton 的八个节点，FP32 `(1 + BF16 weight)`、缩放及乘权，再 terminal BF16 RNE。没有改成 GDN Norm 的串行256累加或 sqrt/div。

RoPE 复用 B1：前32与后32配对，仅旋转64维；四个乘积分别 BF16 RNE，两次加减再 BF16 RNE，其余192维逐位保留。Q gate 也逐位保留，包括不参与算术的 opaque 编码。

`BlockScalarFloat` 仅新增真实 primitive exception flags 旁带，伴随原 Add/Mul result 在反压时稳定。原 result/error 语义不变；复合算子不能伪称拥有一条原生 ALU flags。旁带通过 Qwen2ContinuousBlock 的现有独占服务到两个 owner。

## 当前已验证边界

- 共享 Scalar：原77向量与20个异常/舍入位级向量通过。
- Norm owner：cold0/carried127 共20头，25800个真实 Scalar 请求、结果、flags 与原 integer/C 逐位一致；Norm、gate、mean/epsilon、inverse、ACK fence 均通过。
- RoPE owner：两个绝对位置0/255、Q8/K2，共3840个 Scalar 节点及3840个 BF16 边界逐位一致；实际 ACK 输出与参考逐字节相同，192维尾部无变化。
- 协议负例包括非法 shape/dtype/范围、缺失 flags、读写/tag/数值故障、最终 ACK、memory/Scalar/completion 反压，以及部分 staging 已 ACK 后 reset 后的新 job。
- 最新四个公共 Scala 文件编译通过。Host 前端使用测试替身完成 owner，七命令绑定、28种 done 故障、物理 alias、真实 producer 依赖和默认关闭行为通过；这是 CONTROL ONLY。
- 公开 descriptor、live reference authority、物理 artifact 审计及 CI 编排共190项测试与120个 subtests，普通和 `python -O` 均通过；计划/清单91项通过。这些 Python 控制测试不执行 fresh capture 或生产 RTL。

本地 owner 输入复用之前已经核验的真实生产 QKV 输出，不是新的官方 capture 或新的 Matrix 执行。fixture manifest SHA256 为 `890da192e5d11d95661db68e5b3b8210f205ac165a8ed12a0bad952160e413ab`。原 model revision `2fc06364715b967f1860aea9cf38778875588b17`，Transformers revision `14e738b5d0cc69aa27a95dde272aea41fde44f2f`。旧源字节按精确 commit/path 或冻结 override 的 SHA 核验，未将旧 PASS 绑定到新源码。

## 持久 CI 与后继工作

新 workflow `host-bf16-qkv-rope.yml` 计划在同一个180分钟 job 中完成小门禁、官方固定源 fresh capture、同输入的 integer/C 投影及 Norm/RoPE 参考、一次生产构建、cold0 的正常/故障/恢复和 carried127 正常执行。所有真实中间 allocation 从哨兵开始，只初始化 raw input、权重与常量。case 之间是否 reset 由实际驱动记录；同一七命令 case 内不得注入参考中间输出。

runner 使用9000秒总预算并为失败回执留120秒；每个 case 的超时写明 mode 和 exit，不把超时记为通过。新 read-fault 两项分别发生在末次 RoPEK 的 NormK 输入和 trig 常量；恢复用例是 Q 的首 activation 读错之后同一 DUT/DDR 从头执行七命令，未声称新增 Dense weight fault 或中途 state checkpoint 恢复。

只上传两份紧凑 JSON：summary 与 source/input/output hashes；权重、NPZ、张量、RTL、可执行文件及完整 DDR dump 留在 CI 工作盘。fresh capture 与复用计数分别报告；跨环境官方 prefix 输入可能存在字节差异，不宣称跨主机 bit-exact。原 native full audit 失败、Norm 原阈值和 native-conditioned RoPE 精确规则继续保留。

该子链输入仍是官方前缀到达 layer3 的既有归一化输入；layer3 input RMSNorm、真实 prefix KV、QK/softmax/PV、sigmoid gate、O projection、residual、postnorm、FFN/down/residual 均未由此门禁覆盖。cold128/carried128 全 M128 仍待生产整链执行，后续工作应接这些依赖；不启动孤立的九小时候选来替代生产 Host 集成，也不关闭完整 block 或三模型目标。
