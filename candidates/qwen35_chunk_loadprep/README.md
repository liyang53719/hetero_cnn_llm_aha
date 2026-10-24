# 私有 chunk phase1：LoadPrepAndCumsum

本批新增一个独立 `GdnChunkLoadPrepOwner`。尚未编译、展开或执行 Chisel。模型测试须先独审，再由 root 单次执行；当前没有测试 PASS 或硬件数值资格。

实现范围仅已 pin 的 `chunk/model.py:380–406` 完整阶段：一个 head/chunk 的 64 个顺序 FP32 Add 请求，随后按 gate、Q、K、V、row/beat 原顺序写私有 scratch。无 derived QK/exp/Matrix/solve/state update，不发布 root/generation，不抬 public M1/recurrent/Host 拒门。M16 的 padding 没有输入读，但仍执行 Add(+0) 并写满全部 64 行。

## 算术与接口

- 复用 `GdnScalarClient`，仅 `ScalarOp.Add=0`，未实例化任何算术单元、Vector 端口、SRAM 或 DMA。只有一拍 512-bit payload 与 32-bit cumulative，以及控制/计数/身份寄存器。Q 已由 prep 缩放，此处仅逐位搬运。
- 固定 legacy ascending binary32 RNE，tininess after rounding，mask30 的既有错误政策；仅接受 vectorPolicy=0。cumulative 每 head/chunk 从 +0 开始；没有树形、FMA、FP64、compensated cumsum 或省略 padding Add。软件原为 Vector16 一活跃 lane，此处映射已有 scalar，数值原语对应需与实际实现资格分开，资源调度并不相同。
- exact subnormal 与 signed zero 是有限合法结果，不能仅凭 exponent=0 判 underflow。原 scalar 通过 error 报失败，不提供 tag 或 raw flags。Python 小控如注入 error，只是服务故障替身，不宣称自然 Add 产生 inexact tiny underflow。
- MemoryRequest/Response 均没有 nbytes。写请求为全 64-byte mask；固定拍义依赖原 fabric。响应错 tag 优先 Protocol7，matching error 为 Memory3。数值非有限/非法 gate 为 Numerical8。所有读拍 16 words 均检查有限；gate 后14 words 必须原始 +0，g 非正、beta∈[0,1]，前两字允许 ±0。
- 内存和 scalar 不重叠，每次只有一个 outstanding。request.valid/!ready 稳定，响应仅 wait 状态消费；提前响应必须由对端 held。仅成功 write ACK 记写字节/推进。scalar request fires 和成功 finite returns 分别计数。

## 来源与阶段门

输入 `prepReady` 是新私有 scheduler 封装：同 tag/generation/tokens/input，状态成功、完整 tokens×25600 write ACK、preparedComplete/drained、非 recurrent。现有 prep 接口没有 generation/input 字段，不能假称本批已接上真实 producer。

chunk0 必须有同身份/head 的 phase0/chunk0 initial receipt，scratch ACK65536、无 output/state ACK、成功 drained。chunk1 仅 M128，必须有同身份/head 的 chunk0 phase16 scratch ACK65536 和 phase17 output ACK16384；不能用 stateOut 代替。receipt 本身不证明来源，也没有全局锁；scheduler 必须验证真实完成链并独占、保持所有根和源数据稳定直到本 job 结束。

每次准入仍核五个完整 disjoint spans、64B 对齐、56-bit exclusive end（恰 2^56 合法）、M16/M128、head/chunk、cold/warm root generation 与 generation!=0xffffffff。地址沿已验证 AddressPlan，不改变其24矩阵布局。

成功只产生 phase1 receipt：scratch ACK102400、output/state ACK0、Add 请求/成功返回各64、无 outstanding。末 ACK 前不能完整。终态所有字段和 cycles held 至 done.fire。失败可能留下私有部分写，不回滚/不发布，done 消费后锁定；恢复须同时排空或复位共享 scalar 与 transport。成功再入仍依赖原单请求唯一响应/无遗留返回合同，不声称防重放。

## 数量与固定资源口径

每 head/chunk 固定1600写ACK、102400B。M16有效16行：400读/25600B；M128每chunk有效64行：1600读/102400B。M16全16head为1024 Add、6400读、25600写；M128全32head/chunk为2048 Add、51200读、51200写。

既有 scalar Add 的 request→normal→result→下次request 最早相隔3槽。本版无重叠，理想无 stall 工作槽 `2*(reads+writes)+3*64` 为每 head/chunk4192或6592，但还需加实际FSM转换、fabric/仲裁/DDR/背压和held终态；不是实测cycle/频率/wall上界。利用率分母必须为完整block全周期，不能只用64个ALU计算拍或192服务槽，不报80/90%。

## 小控资格与执行边界

`loadprep_model.py` 是 Python 显式握手模型，`tests.py` 驱动的是它，不是 Scala/Chisel。即使模拟服务按整数实现 binary32 RNE，也不是独立硬件 FP32 数值验证，更不能称 Treadle、真实 ACK、RTL 或 chunk/fullblock PASS。固定手算舍入/zero/subnormal样例只约束替身服务；其余模型返回不替代实际共享 Scalar 的数值验收。

小控只读固定小源码，禁止 native、网络、子进程和文件修改；原数值模型仅读文本，不 import/运行。已核 raw bytes 加载本地模型，避开未 pin pyc。全部 own/external pins 前后核。精确命令及建议上限在 `TEST_COMMAND.json`：目标 CPython3.12、外10s、单CPU、256MiB；root 另行单次准入，作者不执行。当前 Treadle 缺失依赖仍暂停，无网络绕行。

原 Qwen2 full 执行/清理 UNKNOWN 及所有旧失败证据保持不变。本批仅新增独立源码，不触及冻结候选/输入/输出。
