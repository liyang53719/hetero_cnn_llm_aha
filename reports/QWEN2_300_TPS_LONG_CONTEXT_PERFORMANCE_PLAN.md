# Qwen2 >=300 token/s 长上下文与性能统一整改计划

状态：APPROVED，作为 `ARCHITECTURE_AND_EXECUTION_PLAN.md` 的性能整改
overlay；原 L0-L11 依赖和正式门禁不降低。

## 1. 目标和唯一性能口径

- 模型固定 `Qwen/Qwen2-1.5B-Instruct` revision
  `ba1cf1846d7df0a0591d6c00649f57e798519da8`。
- 主门禁为 Batch1 q1024 prefill：完整28层、final RMSNorm、仅最后一个
  token 的 LM head、1 GHz、DDR read/write 100/40 GB/s。
- 使用 integrated RTL/controller cycle-accurate trace；分析数字不得写入
  measured 字段。
- `tokens/s = 1024*1e9/integrated_cycles`；PASS 要求 cycles
  `<=3413333333`，即 `>=300 token/s`。
- q128/q384采用相同RTL、权重、DDR模型和统计口径，并要求：
  `latency128 < latency384 < latency1024`，且
  `token/s128 >= token/s384 >= token/s1024 >=300`。
- 同时要求 1 GHz setup WNS>=0、SRAM<=4 MiB、DDR不超限、0 unresolved、
  0 unmapped；否则性能整改不关闭。
- L11量化路径500 token/s门禁保持不变。

## 2. Descriptor v3 与长上下文合同

128-bit command保持不变；schema v3向后兼容v2，并增加：

- `0x04 shape2_32`：两个32-bit dimension；两条可表示rank4。
- `0x13 attention_op`：backend、block、Q/KV heads、head/rotary dimension及
  固定tile geometry。Full attention仅允许hierarchical block128。
- `0x14 moe_policy`：expert数、top-k、shared expert、intermediate和weight
  format；一期仅供Qwen3.5 compiler/分析模型。
- `0x15 delta_policy`：QK/V heads、state维度、conv kernel、state dtype；
  当前RTL必须返回unsupported status 4。
- `0x32 kv_context32`：32-bit sequence ID及layer/head字段。
- `0x33 kv_range32`：32-bit token_start和token_count。
- `0x34 kv_table`：页表tensor索引、physical-page limit、page-ID位宽、
  levels和page_tokens。
- `0x35 kv_epoch32`：32-bit generation和logical-page count。

固定KV实现：

- 16 token/page；两级radix页表，每级10-bit index。
- DDR PTE为128 bit：physical page ID32、generation32、refcount32、flags16、
  format8、reserved8。
- Root、leaf、PTE和KV data全部驻DDR。
- 片上固定64-entry 4-way TLB、4-entry leaf cache和512 KiB staging，不随
  context线性增长。
- 地址64 bit；token/page ID32 bit；cycle/byte/update/watchdog均64 bit。
- 10k关闭页表和短payload RTL smoke；1M只做地址、守恒、OOM/COW/stale
  generation和分析模型，不跑完整dense attention。

## 3. 数据通路整改

### 3.1 Universal hierarchical block128

- 删除无限单链调度；所有长度自动按128-token block执行。
- 现有token-update datapath仅作为block内部运算。
- 新增独立M/L/O summary merge micro-op；不保留legacy分支。
- <=128只有一个block，无merge；q384及后续hash重新冻结。
- q1024必须复现已通过候选：43008 merges、无score matrix、max error
  `0.000612999275 <=0.002`。

### 3.2 4-context BF16 Matrix interleave

- 保留单个16x32、512-lane BF16/FP32阵列。
- 增加四个accumulator context、2-bit tag、返回scoreboard和bypass。
- 四个独立输出tile轮转，同一context重访间隔>=4 cycles。
- Pipeline填充后每周期accept/complete一个512-MAC step；持续512
  MAC/cycle。
- Context状态约8 KiB，计入4 MiB预算。
- 门禁覆盖依赖context、随机backpressure、tag、异常和至少1M steps。

### 3.3 Matrix blocked FlashAttention

- Query tile固定16x128，key microtile固定32x128，softmax block固定128。
- QK由Matrix生成16x32 score tile；score只进入2 KiB局部buffer并直送
  SFU，不写DDR。
- 四个microtile形成block summary，再执行hierarchical merge。
- PV复用同一Matrix，输出16x128 O block。
- Q/K/V及probability的BF16边界和FP32 accumulation顺序由Python/C++
  golden冻结；若BF16 probability不满足0.002，固定增加FP32 probability
  input转换，不允许回退串行dot128。
- q384 Attention目标<=1.5M cycles；q1024按真实block测量。

### 3.4 8-lane fully-pipelined fused SiLU times up

- 八个FP32 SiLU lane；exp2/reciprocal accept interval=1。
- 每周期接受八组gate/up，直接输出`SiLU(gate)*up`。
- 不写回SiLU中间tensor；保持现有PWL、reciprocal和RNE语义。
- q384目标<=0.5M cycles；q1024按9175040 scalars实测。

### 3.5 Tile级DMA/Matrix/SFU重叠

- 内部micro-op固定为load-weight、load-activation、matrix-context-step、
  QK-tile、softmax-update、summary-merge、PV-tile、SiLU-product、store。
- 公共ISA不暴露local address/context ID。
- Activation ping-pong每份4 KiB，weight每份8 KiB，score tile 2 KiB。
- DMA/Matrix/SFU独立queue depth16；DMA prefetch distance2，outstanding8。
- SFU处理tile N时Matrix执行N+1、DMA预取N+2。
- 每层权重每个prefill request只从DDR读取一次，不得按16-token batch重读。
- 100k随机transaction无丢失/重复/reorder/deadlock；要求
  `overlapped/serialized <=0.65`，Matrix有效利用率>=85%。

## 4. 固定执行顺序

1. Schema v3、32/64-bit合同、universal block128 golden、DDR KV页表模型；
   v2回归继续PASS。
2. Universal hierarchical softmax RTL及q128/q384/q1024重新冻结。
3. Context4 Matrix RTL、tiler和1M-step II=1门禁。
4. Blocked FlashAttention QK->softmax->merge->PV。
5. 8-lane fused SiLU-product。
6. Tile scheduler、双缓冲、三队列、100k并发门禁。
7. One-block numerical、4-layer subset、28-layer full trace和q128/q384/q1024
   性能门禁。
8. 未达300时只按Matrix bank/context、Attention balance、SiLU stall、DMA
   overlap顺序修复；不降频、不省DDR、不改口径、不使用另一版RTL。
9. 性能关闭后立即运行L10 early/full PPA，再完成Qwen3.5一期审计。

## 5. LC、SRAM和L10

- LC固定 `/home/yang/tools/synopsys/lc/O-2018.06-SP1/bin/lc_shell`。
- 该程序是Docker compatibility wrapper，输出必须位于挂载的
  `/home/yang/...`，不能写容器`/tmp`。
- 已验证SP6144x128 Liberty可生成DB，且DC X-2025.06-SP3可`read_db`。
- 项目wrapper必须给Docker设置`--cpuset-cpus=8-23 --memory=30g
  --memory-reservation=24g`，输出到ignored `work/generated/l10_sram/`。
- 正式DB：SP6144x128、SP4096x128、2xDP2048x64组成DP2048x128、
  4xDP4096x32组成DP4096x128。
- 每个wrapper独立link后，再综合Matrix、Attention/SFU、KV、DMA、fabric、
  integrated top。
- 约束1.0 ns、uncertainty0.08 ns、I/O 0.10 ns；DC max cores8。
- q1024/decode4096生成SAIF；无有效SAIF不报告energy/token。
- LC只关闭DB。Memory compiler `lef-fp`仍在
  `ReplaceDummyPinsWithObs()`崩溃；正式L10必须等待vendor LEF或兼容ARM
  修复版生成器。GDS/手写abstract不得冒充LEF；此前仅关闭readiness。

## 6. Qwen3.5-35B-A3B分期

一期固定官方revision `59d61f3ce65a6d9863b86d2e96597125219dc754`，
只完成descriptor/compiler/分析模型：

- 40层：30层Gated DeltaNet、10层full attention；hidden2048。
- Full attention：16Q/2KV、head_dim256、partial RoPE64。
- DeltaNet：16 QK heads、32 V heads、dim128、conv4、FP32 state。
- MoE：256 experts、top8 routed +1 shared、intermediate512。
- Native context262144；1M只做分析/地址合同。
- 冻结route trace、active weight/KV/state bytes和cycle模型。
- DeltaNet/MoE backend在一期RTL中返回status4，不假装执行。
- Vision和MTP只登记inventory。

完整文本RTL放二期：需要DeltaNet state engine、conv4/gating、MoE router、
expert dispatch/cache和expert batching。单512-GMAC/s BF16阵列对3B active参数
的理论上限约171 token/s；二期必须使用W8/W4或多cluster，不能拖延本期
Qwen2 300 token/s与L10。

## 7. 资源、证据和提交纪律

- 所有compile/test/sim/DC绑定`taskset -c 8-23`。
- 默认8核；单仿真最多4 threads，可并行两个；审计后峰值最多16核。
- 启动前`MemAvailable >10 GiB`；MemoryHigh24G、MemoryMax30G。
- 磁盘低于50 GB停止新任务；长任务阻塞等待，不做定时轮询。
- 数值失败定位首个节点，不放宽0.002；timing不以false path掩盖。
- 每个子门禁更新result、MASTER_LEDGER、NEXT_ACTION和<=200行HANDOFF，
  形成可恢复commit并立即push。
- 永不提交用户文件`prepare_aha_ast_tools_runtime.sh`和
  `prepare_aha_halide_runtime.sh`。
- measured、cycle-accurate、post-synthesis、analytical四类证据严格分离。
