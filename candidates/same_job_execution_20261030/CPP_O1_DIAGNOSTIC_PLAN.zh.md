# O1 同硬件共同 ELF 改进：待源码独审，非数值 PASS

## 已闭环的五块实际有界诊断

原 executor `dcc3a4b1f1606f2c79e49db5e08d9b38251f80dd`，builder `e01529eb9681fc08a2790d2cc8c17735c986610f`。唯一 controller exit 2；五块都真实启动同一 ELF，原严格收据/cleanup/EOF、完整聚合已独审。全部 `STARTED_TIMEOUT_INCOMPLETE`，不是数值 mismatch，也不是完整执行通过。128 token、完整4096资源未变。Python完整参考与当前仿真数值结果严格分层。

| Profile | 最后 active cycles | 外层秒 | active/外层秒 | 本窗采样 RSS B | census 累计秒 |
|---|---:|---:|---:|---:|---:|
| P0 | 16704 | 309.015 | 54.056 | 285220864 | 305.748 |
| P1 | 17344 | 310.618 | 55.837 | 216649728 | 307.202 |
| P2 | 16960 | 308.124 | 55.043 | 209367040 | 304.806 |
| P3 | 17472 | 312.447 | 55.920 | 1860333568 | 309.033 |
| P4 | 17216 | 311.536 | 55.262 | 1845534720 | 308.070 |

五块均pc0/owner完成0；有读入但无完整输出。完整 block 周期分母、余下时长和MAC利用率均未知，不能由这些值声称架构性能或死锁。P0首命令为原FP32 input_norm；纯源码下界仅其部分子链已≥2,232,320 cycles/128行，当前16704 cycles尚不足该子链首行17440下界。按当前速率不变换算约11.47小时只是条件下界，不是实测完整耗时，更不是可批准的完整预算。

## 下一最小改变

为原冻结SV/driver建立明确新编译策略 `CPP_O1_STRICT_V1`，不改任何Chisel/RTL、ABI、物理资源、刺激、参考、FP32/BF16顺序或舍入。候选所有child/host/driver统一：

- OPT_FAST=-O1、OPT_SLOW=-O1、OPT_GLOBAL=-O1。
- 单一 argv 项 `CXXFLAGS=-O1 -fno-fast-math -ffp-contract=off`。
- 无 Ofast、fast-math、native ISA、LTO、PGO，不接受额外/后置覆盖。
- 旧O0收据继续按旧精确policy与producer身份验证；新policy不能靠自报字段通过，需实际native编译argv、生成make规则、编译器/所有来源锁和新的ELF身份闭环。
- flags只是限制允许的编译变换，不是全生成C++无UB或数值等价证明；新ELF必须重新ABI及全部五块精确数值验收，不迁移任何旧PASS。

原七件只保留五个archive/link阶段成本，合计wall842.054秒；最大已采样RSS3,907,825,664B（Dense child），host archive wall614.844秒。缺全20stage完整成本，不能凭空合成。O1编译峰值与耗时未知；原build7200秒包含prep（仍更紧1800），workflow9000秒及原资源限不扩大。若实际不足，沿本次身份诊断，不缩硬件、不自动重试。

监督器候选仅减少每entry Python对象开销；保留每轮所有root全census、fresh lstat、原顺序/去重/限额/cleanup/采样语义。先以合成小树差分测，不用DirEntry缓存、不降频、不把只读约定当硬隔离。约99%外层时间落在census说明监督主线程开销；DUT自身接近满核，尚不能据此归因DUT慢或保证优化提速。

## 停止条件与下一完整模式

本次源码候选完成精确policy/生产与消费锁、轻测及独审后，由唯一writer发布并启动一次新的共同ELF构建。新的实际速率与资源证据用于完整模式预算；不能重复无解释的300秒资格循环。现有FULL工程预算尚未形成，并非缺用户授权。新构建后必须先确认SV/driver仍逐字节等已验原件，真实编译身份与所有五块共享新ELF完全相同。
