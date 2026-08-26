# Luna Agent 本地执行合同
## Matrix Engine + CGRA/SFU + KV Memory Engine

版本：2026-08-24 v0.1

本文件是执行合同，不是建议清单。Agent 必须按 stage 顺序关闭门禁，不得在 upstream baseline 失败时继续修改第三方代码，不得把 analytical estimate 当成 RTL result，不得使用 Vivado 综合结果替代 22nm Synopsys DC 结果。此 checkout 的编译、仿真、测试和综合命令统一使用 `taskset -c 8-23`；当前主机若只有 CPU 0-23，实际生效集合为 8-23。

## A. 目录和分支规则

建议工作树：

```text
<workspace>/
├─ delivery/hetero_cnn_llm_aha/       # 本交付包，允许修改
├─ work/upstream/                       # 第三方原版，baseline 阶段禁止修改
│  ├─ chipyard/
│  ├─ gemmini_audit/
│  ├─ aha/
│  ├─ idma/
│  ├─ pulp_axi/
│  ├─ common_cells/
│  └─ imax3_llm/
├─ work/forks/                          # baseline 关闭后才创建的 fork/worktree
├─ work/generated/                      # generated RTL/bitstream/filelists
└─ work/results/<stage>/                # 所有日志和报告
```

分支：

```text
baseline/<repo>-<commit>     只记录原版复现，不提交修改
adapter/matrix-v0            外部 wrapper；不改 Gemmini
adapter/aha-sfu-v0           外部 wrapper；不改 AHA
feature/gemmini-standalone   确有必要时的最小 upstream patch
feature/aha-sfu-ops          PEak/Lake/Canal 扩展
feature/kv-engine-v0         clean-room KV RTL
integration/hetero-v0        顶层集成
```

硬规则：

1. `work/upstream/*` 在 baseline 期间 `git status --porcelain` 必须为空。
2. 修改第三方前，保存 commit、submodule commit、tool version、baseline log、generated RTL hash。
3. adapter 优先位于本工程；不能通过 adapter 完成时才建 fork/worktree。
4. 每个 patch 必须有：动机、修改文件、接口变化、原版/修改版回归、license 说明、回退方法。
5. 所有结果必须写到 `work/results/`，终端截图不算验收证据。

## B. 必需工具

最低工具类别：

- Linux、Git、Python 3.11+、C/C++17、CMake/Ninja；
- Docker CE，用于 AHA 官方镜像；
- Chipyard 依赖、RISC-V toolchain、Spike、Java/sbt，用于 Gemmini；
- Verilator 5.028+，同时满足 AHA 当前文档和本工程 lint；
- Icarus 或另一个 SystemVerilog simulator，用于本工程小型 testbench；
- Bender >=0.32、Verible，用于 PULP sources；
- Synopsys Design Compiler；
- 22nm standard-cell `.db`、SRAM macro `.db/.lef` 以及相应许可；
- 可选 Questa，用于 iDMA upstream 自带 testbench。

执行并保存：

```bash
cd delivery/hetero_cnn_llm_aha
taskset -c 8-23 ./scripts/toolchain_audit.sh | tee work/results/toolchain_audit.txt
```

门禁：所有本 stage 需要的工具必须可执行，版本写入报告。工具缺失时只允许标记 `BLOCKED_TOOLCHAIN`，不得生成虚假 PASS 文件。

## L0. 交付包自验证

```bash
cd delivery/hetero_cnn_llm_aha
taskset -c 8-23 ./scripts/sandbox_validate.sh
```

预期输出：

- pytest 全部 PASS；
- `reports/architecture_results.json` 存在；
- C++ smoke 输出 `cpp_reference_smoke=PASS`；
- RTL structural checker PASS；
- command/config/schema 可解析；
- `reports/randomized_reference_sweep.json` 的 `status=PASS`；
- `reports/final_validation.json` 的 `overall_status=PASS`。

验收：

```text
Python tests >= 27 passed
CNN max_abs_error = 0
BF16 paged-KV toy block max_abs_error = 0
INT8 KV error below frozen thresholds
C++ smoke PASS
RTL structural PASS
SRAM partition sum = 4096 KiB
```

失败处理：先修复交付包；禁止继续 upstream 阶段。

## L1. 克隆、锁定和许可证审计

```bash
cd delivery/hetero_cnn_llm_aha
./scripts/clone_upstreams.sh "$PWD/work/upstream"
```

Agent 追加以下文件：

```text
work/upstream/UPSTREAM_LOCK.json
work/results/licenses/<repo>.txt
work/results/licenses/license_matrix.csv
```

许可证矩阵至少列出：repo、commit、license、允许集成方式、是否可修改、notice 要求、输出 artifact 是否可分发。

门禁：

- 所有仓库 commit 可解析；
- submodule 全部初始化；
- tree clean；
- `UPSTREAM_LOCK.json` 不含 branch-only lock；
- 本次执行后将实际 commit 回填 `third_party/upstream_lock.local.json`。

## L2. Gemmini 原版复现

```bash
export CHIPYARD_ROOT=$PWD/work/upstream/chipyard
export OUT=$PWD/work/results/gemmini_baseline
export RUN_SETUP=1       # env.sh 未生成时使用
export GEMMINI_CONFIG=GemminiRocketConfig
./scripts/reproduce_gemmini.sh
```

必须关闭的原版测试：

1. software build；
2. Spike `mvin_mvout`；
3. Spike matmul；
4. Spike ResNet50 或官方可用的 CNN binary；
5. Verilator `mvin_mvout`；
6. Verilator matmul；
7. generated RTL hash；
8. config/parameter header 归档；
9. baseline performance counters（至少 cycle/load/store/execute）。

额外审计并输出 `gemmini_arch_audit.md`：

- `GemminiArrayConfig`/实际 config；
- tileRows/tileColumns/meshRows/meshColumns；
- scratchpad/accumulator capacities and banks；
- input/output/acc types；
- `pe_latency`；
- DMA bus/max bytes；
- load/store/execute queue 和 ROB；
- LoopMatmul/LoopConv 对 `DIM` 或方阵的假设；
- generated top ports；
- RoCC、TileLink、TLB/PTW 依赖。

硬门禁：

- 原版 clean tree；
- `result.json=PASS`；
- `generated_rtl.sha256` 非空；
- 不允许通过修改测试、跳过 compare 或扩大容差获得 PASS。

## L3. Stanford AHA 原版复现

```bash
export AHA_ROOT=$PWD/work/upstream/aha
export OUT=$PWD/work/results/aha_baseline
export AHA_WIDTH=4
export AHA_HEIGHT=16
./scripts/reproduce_aha.sh
```

必须保存：

- AHA root commit 和递归 submodule commit；
- Docker image digest；
- Garnet RTL hash；
- Gaussian map log；
- PnR route/bitstream/log；
- Verilator test log；
- tile count、PE/MEM/IO composition、configuration bits、route utilization；
- Garnet/Lake/Canal/PEak Python package versions。

硬门禁：

```text
aha garnet PASS
garnet.v exists and is non-empty
aha map PASS
aha pnr PASS
aha test PASS
TOOL=VERILATOR
source tree clean
```

如果 Docker `latest` 与 cloned commit 不兼容，记录 image digest 和错误；优先使用该 AHA commit 对应的 branch/image。不得直接升级任一 submodule 使测试“碰巧通过”。

## L4. iDMA/PULP 和 IMAX3 基线

```bash
export IDMA_ROOT=$PWD/work/upstream/idma
export OUT=$PWD/work/results/idma_baseline
./scripts/reproduce_idma.sh

export IMAX_ROOT=$PWD/work/upstream/imax3_llm
export OUT=$PWD/work/results/imax3_audit
RUN_BUILD=1 ./scripts/audit_imax3.sh
```

门禁：

- iDMA Bender dependency/source enumeration PASS；
- AXI read/write backend、outstanding、burst、error response 接口形成审计表；
- 有 Questa 时执行 upstream `tb_idma_backend_rw_axi` simple job；没有 Questa 时明确 `BLOCKED_LICENSED_SIM`，后续必须由本项目 Verilator integration test 覆盖；
- IMAX3 audit 给出 RTL/source/prebuilt artifact 数量和 kernel inventory；
- 只有实际可读、可构建的 source 才进入复用清单。

## L5. Adapter-only 集成

### L5.1 Matrix adapter

创建独立 adapter，不修改 Gemmini：

```text
128-bit command
  → descriptor fetch
  → Matrix micro-op sequencer
  → Gemmini command/RoCC-compatible envelope
  → generated Gemmini macro

shared iDMA/AXI response
  ↔ Gemmini scratchpad/accumulator load/store boundary
```

第一版允许在 Chipyard harness 中保留 RoCC/TileLink，只验证 descriptor→Gemmini operation 等价；第二版才抽离独立 macro。

必须覆盖：

- mvin/mvout；
- matmul WS/OS；
- accumulate/bias/requant；
- conv loop；
- queue backpressure；
- event completion；
- illegal descriptor/status。

验收：同一 input/weight/command 在官方 C library 路径和 descriptor adapter 路径产生相同 output、memory write trace 和 completion status。每个 operand mode 至少有 directed + randomized tests。

### L5.2 AHA adapter

先只包住 generated Garnet macro：

- config/bitstream load；
- 512-bit stream gearbox；
- IO tile mapping；
- real ready/valid skid buffers；
- tensor tag/last；
- event completion；
- reset/config/run states。

验收：Gaussian 在原 AHA harness 与 wrapper harness 输出一致；随机 input/output backpressure 下无 data loss、duplication、reordering 或 deadlock。

### L5.3 KV/iDMA adapter

先实现 BF16 append/read/free，地址请求交给 iDMA backend。不要在本 stage 实现 prefix/COW。

验收：与 Python `KVPageEngine` command trace 一致；物理页边界、unaligned tail、OOM、OOB、free 后复用全部覆盖。

## L6. 共享 Fabric 和事件系统

实现：

- 16-bank shared L2；
- 2 read + 1 write DMA clients；
- Matrix/SFU/KV direct streams；
- bank arbitration；
- event wait/signal scoreboard；
- per-engine in-order command queue；
- performance counters。

随机验证：

- ready 概率随机；
- burst length、bank conflict、event dependency、engine latency随机；
- scoreboard 以 transaction ID、tensor ID、byte enable、last 比较；
- watchdog 验证无死锁。

硬门禁：10,000+ random transactions，0 mismatch，0 protocol assertion，0 timeout；同一 engine in-order，跨 engine 只按 event 约束。

## L7. CNN 功能闭环

按顺序：

1. INT8 GEMM；
2. 1×1 Conv；
3. 3×3 Conv；
4. bias/requant/ReLU；
5. pooling；
6. residual add；
7. depthwise Conv on CGRA/Lake；
8. depthwise + pointwise block；
9. ResNet50 operator subset；
10. MobileNetV2 operator subset；
11. YOLOv5s operator subset。

每个 operator 记录：shape、layout、dtype、scale、input/output hash、cycles、DMA bytes、matrix utilization、SFU utilization、bank conflicts。

数值门禁：

- integer operators：bit exact；
- BF16 operators：逐节点误差阈值由 `spec/numerical_contract.md` 冻结，不能运行后临时放宽；
- end-to-end quant model：与同一 quant params 的 golden 比较，不与 FP32 模型混比。

## L8. BF16 LLM 单 Block

目标模型先使用公开的小型 Qwen/Llama config，但只关闭单 block：

```text
RMSNorm
Q/K/V projection
RoPE
KV append/gather
causal QK
online Softmax
PV
O projection
residual
RMSNorm
gate/up
SiLU × up
down
residual
```

执行顺序：toy shapes → hidden 256 → target hidden/head shape → q128 → q384 → decode context 128/1024/4096。

必须保存逐节点 trace：Q、K、V、RoPE、M、L、O accumulator、OProj、gate、up、SiLU、down、final residual。

硬门禁：

- 不落完整 score matrix；
- M/L/O 为 FP32；
- K/V RoPE 后写 cache；
- GQA head mapping 正确；
- q384 和 decode context4096 无 timeout；
- error thresholds 在运行前冻结并逐节点通过。

## L9. W8A8、W4A8 和 KV INT8

分开实现，禁止一步同时改三个数值合同。

### L9.1 W8A8

- INT8 activation/weight；
- INT32 accumulator；
- Norm/Softmax 仍 BF16/FP32；
- per-channel output scale；
- bit-exact integer reference。

### L9.2 W4 storage / W8 compute

- LPDDR/L2 packed signed INT4；
- G64/G128 scale；
- load path unpack/dequant to INT8；
- MAC throughput仍按 INT8 2048 MAC/cycle报告；
- 验收权重字节减少，不要求 compute cycle 减半。

### L9.3 native W4 dual-dot

- exhaustive all signed nibble pairs；
- accumulator overflow/rounding/saturation；
- random matrix tests；
- 4096 effective MAC/cycle 的 RTL wave/counter 证据；
- DC area/timing/power与 storage-only baseline对比。

### L9.4 KV INT8

- per-token-head scale；
- append quant、gather dequant；
- GQA/MQA multicast；
- long-context error sweep；
- KV bytes/cycle 和 scale overhead 报告。

## L10. 高级 KV 语义

实现顺序：

1. two-level block table；
2. TLB/leaf cache；
3. paged gather coalescing；
4. multi-sequence/layer arbitration；
5. full-page prefix share；
6. partial-page copy；
7. refcount；
8. copy-on-write；
9. sliding window/free；
10. generation ID 防 stale reference。

随机 reference test：软件产生 append/share/fork/write/read/free 序列，RTL 和 Python model 每步比较：length、block table、physical page、refcount、K/V hash、free count、status。

硬门禁：至少 100,000 commands；0 refcount leak；free+allocated=physical pages；无 stale read；COW 后 source 不变；OOM 可恢复并返回明确 status。

## L11. 完整 RTL 与模型回归

目标：

- CNN：ResNet50、MobileNetV2 代表 blocks；
- LLM：Qwen3 0.6B/1.7B 或 Qwen2 1.5B 的单层和可执行模型子集；
- prefill q128/q384；
- decode context 128/1024/4096/更长分页 case；
- batch/continuous requests；
- all engines overlap。

比较层级：PyTorch/llama.cpp → operator golden → Python architecture → C++ → macro RTL → integrated RTL。

结果必须区分：

```text
functional pass
cycle-accurate pass
performance estimate
RTL measured performance
post-synthesis timing/area/power
```

任何报告不得混用。

## L12. 22nm Synopsys DC

先对本工程 contract RTL smoke：

```bash
export STD_CELL_DBS=/path/tt_*.db:/path/other.db
export CLOCK_PERIOD_NS=1.0
./scripts/run_dc22.sh
```

生产 macro：

1. Gemmini/AHA/generated adapter、KV、fabric 分别建立 filelist；
2. SRAM 替换为 foundry macro wrapper；
3. `.db` 加入 link library；
4. 对每个 macro 单独 `check_design/check_timing/compile_ultra`；
5. 顶层再综合；
6. 不把 SRAM bitcell 面积从寄存器推断；
7. 输出 mapped netlist、SDC、QOR、area hierarchy、max/min timing、power estimate、unmapped report。

初始约束：

```text
clock = 1.0 ns
uncertainty = 0.08 ns
input/output budget = 0.10 ns
zero unresolved references
zero unmapped cells
```

硬门禁：

- setup WNS >= 0；
- hold 在同工艺 CTS/hold flow 中关闭；
- no combinational loop；
- no unintended latch；
- no inferred multi-megabyte flop memory；
- SRAM macro 全部链接；
- multiplier/FPU implementation 明确；
- area/power按 Matrix、SFU、KV、L2、DMA、fabric 分项。

若 1 GHz 不收敛，按以下优先级修复：

1. 增加 BF16/SFU pipeline；
2. Matrix tile/mesh boundary pipeline；
3. reduction tree 分级；
4. KV table/TLB path pipeline；
5. 512-bit crossbar register slice；
6. subarray/physical hierarchy；
7. 最后才降低频率或缩小配置。

禁止通过 `set_false_path` 隐藏真实同步数据路径。

## L13. 性能和架构探索

至少比较：

```text
A: 1 × 16×16 Gemmini baseline
B: 4 × 16×16 cluster
C: 1 × 32×32
D: 2 × 32×32 logical 32×64
E: native rectangular 32×64（仅在前述点关闭后）
```

每个点固定：工艺、1 GHz constraint、SRAM总量、外存带宽、workload、quant、compiler版本。报告：

- RTL cycle；
- effective MAC utilization；
- weight/KV/activation bytes；
- SRAM bank conflict；
- SFU/Matrix/KV overlap；
- area；
- setup WNS；
- power estimate；
- prefill token/s；
- decode token/s；
- energy/token（有可靠 power 时）。

目标验收：

- q384 prefill ≥500 token/s/Batch（所选 1.5B 量化配置）；
- decode ≥10 token/s/Batch；
- Matrix useful utilization ≥目标合同；
- LPDDR read ≤100 GB/s target；
- SRAM ≤4 MiB target；
- 所有数值回归通过；
- 1 GHz DC setup closure。

如果 token/s 不达标，必须用 measured breakdown 归因到 compute、weight bandwidth、KV bandwidth、SFU、bank conflict、scheduler bubble 或 synchronization；不得仅扩大阵列。

## C. 统一验收文件

每个 stage 写：

```text
work/results/<stage>/
├─ result.json
├─ commands.sh
├─ tool_versions.txt
├─ source_commits.json
├─ stdout.log
├─ stderr.log
├─ artifacts.sha256
├─ metrics.json
└─ failure_analysis.md   # 仅失败/阻塞时
```

`result.json` 最少字段：

```json
{
  "stage": "Lx",
  "status": "PASS | FAIL | BLOCKED_TOOLCHAIN | BLOCKED_LICENSED_SIM",
  "source_commits": {},
  "commands": [],
  "tests": [],
  "metrics": {},
  "artifacts": [],
  "known_limitations": []
}
```

最终只有所有依赖 stage PASS 才允许标记下一 stage PASS。`BLOCKED_*` 不是 PASS。
