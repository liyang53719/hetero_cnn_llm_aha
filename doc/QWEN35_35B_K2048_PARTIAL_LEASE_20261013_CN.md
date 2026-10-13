# 35B 前置：K2048 双 partial 的实际软件数据链

本批从精确 main `1a59e575d64f59c0d435fbd733bd6d53ffe2947a` 开始。该提交已封存0.8B L3完整cold128→实际carried128软件结果；原payload CI [38344339398](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/38344339398)成功，38正常＋38优化模式测试闭环，未重跑数值或RTL。

本批解决35B hidden=2048所需的真实片上容量及生命周期，直接复用已有typed Dense/Matrix/Vector/内存驱动。当前验收是合成输入的K2048投影软件子算子；未下载35B权重，尚未确定其官方全形状backend归约profile，不算35B完整block、公共Command128或生产Chisel/RTL通过。

## 固定物理资源与 destructive lease

原A SRAM保持16 banks×1376 words×256bits=704512B，每bank 1R1W。Matrix4096 MAC、五context和原16-lane Vector不变；没有第三个tensor槽、影子partial或另一套算术。新增phase/identity/消费计数属于控制元数据，综合面积和时序尚未测，不能因单元数量相同声称这些控制免费。

| 每bank物理区间 | 用途 | 全bank容量 |
|---|---|---:|
| [0,1024) | M128×K2048 BF16 A | 524288B |
| [1024,1184) | M128×N160 FP32 lhs，后被sum覆盖 | 81920B |
| [1184,1344) | M128×N160 FP32 rhs | 81920B |
| [1344,1376) | 未使用余量 | 16384B |

两个完整partial均sealed后，显式新sum identity撤销原lease。每一16-lane beat必须先接受lhs响应，再接受rhs响应并发往同一个Vector Add；只有其真实结果才可对原lhs相应lane做RMW，保留其余7个FP32 lane。下一edge的物理写必须退休才处理下一beat；整个sum完成、所有真实DDR写ACK、释放元数据复核及成功终态接受后，D才能发布。每个bank实际端口冲突检查保持。保留五context的意义是避免主动降为三context；未据此声称吞吐达标。

旧值的phase、identity和index均有检查，不能在消费后重读、并发Dense访问或使用私有slot2别名。abort不能取消已经接受的RMW：先写回该已接受操作，再poison，不公开半sum。reset在bank/Vector在飞时按双方一致的abort排空；之后才能协调复位和重新staging。

## 实际接线、测试及已修缺口

新 `candidates/qwen35_35b_prefill` 模块使用原`down.Banks`对象、MatrixService、Vector16及TypedMemory地址映射。两个K窗口分别写真正FP32 partial；同Vector Add实际读取这些字；最终原BF16 drain写回真实D并接收ACK。K范围/pair次序由显式ReductionProfile携带；本批仅允许synthetic角色，不能借旧0.8B官方profile授权35B。

小算术门覆盖M16/K32/N32、K64/N160、K2048/N32以及N192跨窗，用独立libm fmaf和FP32 Add/BF16 RNE逐字检查。另在同一实例依次执行新投影、普通Dense及seeded Down，确认资源不替换。控制门覆盖完整M128×K2048 A与双M128×N160 partial共存、1280beat生命周期、背压、最后ACK错误、held-success poison、非法slot2/无效Job零步失败、已接受RMW的abort/reset和真实Vector held-result协调reset。

集成曾发现并修复四个真实缺口，原失败日志保留：
- 新bank release清空tag，抹去原owner下一edge要核对的退休凭据；改为仅撤销live/sealed，保留identity/shape/consumed。
- inherited窗口终态仍以三个槽检查非法slot2，导致两槽越界；新owner显式两槽界并保留零步MAC安全条件。
- 原typed authority尚未列出新owner，混模式实际驱动拒绝；增精确类型分支，旧owner先返回，旧闭包不加载新实现。
- connected reset在Vector持有结果时两端对reset/abort采样不一致；新包装在两端统一先abort排空，不能直接清除控制状态。

最终冷源GDN 387项/27套与Attention 247项/23套全通过；其中新bank 22项、实际投影16项。独立review的10份源码hash与最终冷副本、当前源码完全相同。[紧凑回执](../reports/execution/QWEN35_35B_K2048_LEASE_20261013.json)保留库/源码/逐suite日志hash。生成目录与原工作区分离，数值库从本次源重新构建，未读取旧模型capture或旧编译库，未重跑官方M128、未生成RTL。首轮冷副本自身386+247项通过，但因review期间工作树后继修改而被source-drift总门标FAILED，未把该身份冒作最终通过；修复后的完整顺序冷门重新封存。精确远端CI待本批发布后核验。

## MAC与占空比口径

四个合成投影的测试日志各输出`K2048_CASE`机器可读记录，包含实际Matrix FMA delta、partial结果的useful MAC合计、Vector Add请求/活跃lane操作、实际读写/ACK计数、输入输出hash和软件tick。固定分母资源为4096 MAC、16 Vector lanes、五context。软件tick与宿主秒数都不能当完整硬件周期；完整cycle、Matrix/Vector busy、active-lane占空比、供数/依赖/写回/调度空闲与跨tile重叠均为unknown，等待同源周期模型或后续冻结RTL回放。

K2048容量与五context是可实现性条件，不是80%/90%利用率证明；当前两个partial依次计算、Vector破坏性归约、最终写回仍有明显阶段依赖。流水候选必须保持双方operand真实消费、1R1W及错误排空，不能消除尚未读取的partial。

| 合成M16子算子 | useful MAC | 实际C++执行FMA | 软件tick | 实际D ACK |
|---|---:|---:|---:|---:|
| K32/N32 | 16384 | 131072 | 814 | 1024B |
| K64/N160 | 163840 | 1310720 | 4156 | 5120B |
| K2048/N32 | 1048576 | 8388608 | 14202 | 1024B |
| K32/N192跨窗 | 98304 | 786432 | 4074 | 6144B |

这些是有背压的合成投影小门，不是完整35B block，也不是M128性能；软件tick不能用于该表的硬件MAC利用率计算。

## 状态与下一步

- done：双N160显式物理lease及真实共享算术/写ACK小闭包，旧默认路径回归。
- done：冷完整634项轻门与源码独立审查。
- ongoing：精确发布CI闭环。
- todo：固定35B最小原始embedding/权重范围与官方全形状backend证明；确定K2048通用归约profile后接实际RMS/QKV。
- todo：35B L0的32 value heads/FP32状态与MoE top8真实路由及shared expert，L3的真实L0–2前缀、16Q/2KV和MoE，随后完整M128模型。
- todo：对应Chisel内部lease/窗口/错误退休控制接线和默认关闭小门，公共Host与最终冻结RTL回放；当前Python执行不冒充这些硬件已实现。

C03.2/C04.2/C05仅推进实现子门；Q35C/Q35D/U00.2/U01及五block总门不关闭，原数值失败不改写。
