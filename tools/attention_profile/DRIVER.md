# Frozen Attention core diagnostic driver

## 当前诊断范围

本入口只定位精确 `6959810545203d5f9508075b311dba52f1bee0c9` 的生产 Attention core 仿真为何在原 3600 秒 case 上限内仍处于首个 Q 投影。现有尾日志显示实际读请求持续前进，尚不能确认最后是否停顿，也没有数值反例。新 GQA 的未激活组合求值成本是待验证假设。

诊断复用同一完整 HostBlockTop、Matrix512、iDMA、官方来源及原夹具；功能 RTL 必须与原失败版本的 SHA256 相同。只增加 `eval` 与夹具执行时间、实际周期和握手计数，运行两次相同的 4096 周期前缀，每次上限 240 秒。前缀确定性通过不等于完整数值链通过；`numerical_acceptance` 始终为 false。测量包括插桩开销，不能称原始未插桩性能或 MAC 利用率。

运行前先核对两个独立 checkout：GitHub 触发提交绑定本诊断源码，冻结的 695981 提交绑定生产源码。仅独立 source worker 适配旧入口的单一 `GITHUB_SHA` 检查，摘要同时保留真实触发提交和两个源码身份。未修改 hierarchy；只有测量支持相关假设后才考虑模拟编译边界。完整 block、M128 和原官方精度门禁的状态不由本诊断改变。

首次诊断 [run 37944430478](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/37944430478) 在构建成功后被原始 SV 字节哈希准入拒绝：生成值 `4d20ce579a2e8bb9598cd71e1b5187fe70f131992849507f077a154944269dbd`，要求值仍为 `4f061c48397979339ff97bef5a5e9f9dee2bd4a0dec7a5637f8a95b5de2e45f9`。构建耗时 1518.05 秒，前缀执行次数为零，没有性能结果。原失败保留，不能记为数值失败或通过。

已有生成 SV 证实源码相对目录会进入 source-location 注释及其排序；本次 SV 原文未保留，因此尚不能断言差异全为注释。修正后冻结生产 checkout 位于原 CI workspace 根目录，诊断 checkout 位于其 ignored `work/attention_profile_diagnostic` 下。原 SV SHA 硬门禁前移到 emit 后、Verilation/C++ 前；即使只有注释变化也必须拒绝，不做字符串归一化或更换期望 SHA。再次运行仍只算诊断，是否恢复必须看其实际结果。

恢复诊断 [run 37949433235](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/37949433235) 已成功匹配原 `4f061…` SV。两次同 ELF、同输入的 4096 周期各耗时 92.08 / 92.41 秒，其中 RTL `eval` 占 99.760% / 99.762%，其余夹具和插桩约 0.22 秒；80 次 AR、794 次 R、80 次 Matrix issue 与完整确定性摘要一致。619 项生产源码、10 项诊断源码及 7 项实际输入哈希已核对。该结果定位到顶层 RTL 求值成本，尚未定位具体模块；官方 baseline / AVX2 整层仍分别有 6 / 5 项原阈值失败。

后续 `--gqa-boundary-ab` 实验在同一个 job、同一份 fresh fixture 上顺序构建 baseline 和 candidate，各测两次相同前缀。candidate 只在复制的 Verilator 配置末尾增加 `hier_block -module "Bf16CausalGqaOwner"`，原配置不改；两版生成 SV 都必须匹配原硬 SHA，实际 build stage 必须出现该新分层，编译器、严格 FP 参数和所有输入保持一致。两个 build 共享原 7800 秒总预算，各自最多 6000 秒且受剩余预算约束；四个前缀仍各最多 240 秒。仅报告本机顺序测量的 eval/build 比值，前缀、事件 SHA 或原 driver 日志任一不等均拒绝。该 A/B 已在 8a937ead 实测完成，候选 eval 均值慢 70.79%，明确不采用；完整来源与负结果见 [中文记录](../../doc/U00_2_HOST_ATTENTION_PROFILE_AB_8A937EAD_20261009_CN.md)。本诊断不构成完整数值链、M128 或硬件 QoR 验收。

This generator only instruments the simulation driver. It does not emit RTL,
change hierarchy or resources, introduce a command variant, preload references
into the DUT/store, or run the production top. A successful bounded prefix is a
diagnostic result with `numerical_acceptance: false`.

## Source and build contract

Run from a checkout containing the exact frozen Git objects:

```sh
python3 tools/attention_profile/generate_profile.py \
  --repo /absolute/frozen-source-checkout \
  --output /absolute/new/instrumentation \
  --cycles 4096
```

The generator reads `git show 6959810545203d5f9508075b311dba52f1bee0c9:<path>` and
checks complete SHA256 pins for `host_bf16_attention_core.cpp` and
`host_physical_axi.h`. The former is emitted byte-for-byte unchanged, including
its constructor, all public launch construction, reference audits, physical
memory, backpressure, and error checks. Both original sources are also retained
in `original/`.

The generated header differs by exactly five reversible edits: a timing-header
include, a timer at entry to `PhysicalAxi::step`, and substitutions at the three
existing `d.eval()` sites. The first records the same pre-edge handshakes the
original service consumes. The last records the finished step and stops at the
fixed prefix after all original physical-store/ACK bookkeeping and the final
falling-clock evaluation. No additional DUT evaluations occur.

Use generated `profile_driver.cpp` as the single C++ translation unit in place
of the original driver argument. Keep the original production RTL, emitter,
filelists, resources, hierarchical build recipe, and compiler flags unchanged:

```
-O2 -std=c++17 -ffp-contract=off -fno-fast-math
```

The generated `.cpp` includes the exact original under a renamed `main`. Its
wrapper catches only the dedicated non-`std::exception` prefix sentinel as
success. Assertions, driver errors, bad modes, invalid paths, and unexpectedly
finishing the complete workload before the prefix are failures. This generation
receipt alone cannot prove the RTL or compiler identity; the build orchestrator
must verify those against the frozen source and actual emitted build commands.

`transformation_receipt.json` records the exact replacement strings, source pins,
generator SHA256, hashes of every generated file, compile path, and CLI contract.
Generation rejects reused/symlink outputs and malformed/out-of-range cycle
limits. The fixed compiled bound is 37–65536 cycles, normally 4096. It includes
the original six reset and thirty idle constructor cycles. No runtime option can
extend the compiled bound.

## Runtime and reports

The binary preserves the original CLI:

```sh
VHostBlockTop FIXTURE FRESH_OUTPUT [pass|cache-v-write-error|context-write-error]
```

The original constructor creates `FRESH_OUTPUT`. Instrumentation writes:

- `attention_profile.json`: status, timing, cycle/eval inventory, handshake totals,
  and deterministic terminal counters
- `prefix_events.jsonl`: deterministic per-cycle comparison input with no timing,
  filesystem paths, or raw payload data

The successful schema has `schema_version: 1`,
`schema: HOST_ATTENTION_PREFIX_PROFILE_V1`,
`status: BOUNDED_DIAGNOSTIC_PREFIX`, `prefix_reached: true`,
`cycles == cycle_limit`, `eval_calls == 3 * cycles`, and
`numerical_acceptance: false`. Exit status 0 means only that this prefix was
measured. Any other exit, a missing final report, or `PREFIX_RUNNING` is not
successful diagnostic completion.

`eval_ns` measures just the three actual `d.eval()` calls using a monotonic
clock. `step_elapsed_ns` measures the entire instrumented physical-service
steps. `driver_excluding_eval_ns = step_elapsed_ns - eval_ns`; it includes
instrumentation, event hashing/serialization, existing driver logging, and prior
checkpoint writes. It is not a measurement of the uninstrumented driver's cost.
Per-phase call/timing arrays expose the three evaluation sites. The entire
wrapper wall time additionally includes DUT construction, fixture loading,
original audits outside steps, and teardown. The final report write is outside
the per-step measurement. A failure report explicitly counts an incomplete step.

A partial report is atomically replaced after the first completed cycle and every
64 cycles. Those reports exclude their own current write cost; final accounting
includes all prior checkpoint writes. A process killed by the external wall-time
limit retains the last flushed prefix and cannot claim acceptance.

`deterministic.terminal_event` includes original PC/run, public matrix pipeline
issues/stalls, metadata ownership, iDMA progress, bus accepted/read/write/ACK
counts, pending transaction state, completion/result state, and physical store
byte counts. First-evaluation handshakes describe the transfers used by the
original step. End-state values are sampled after the third evaluation. The
matrix observation is the existing public `io_pipelineIssues` (`wideSteps`) and
`io_pipelineStalls`, with no private hierarchy access. Lack of progress remains
visible; instrumentation does not infer or synthesize progress.

Compare the complete `deterministic` objects and SHA256 of the exact
`prefix_events.jsonl` bytes across two runs of the same ELF/fixture. Every event
contains only counters/handshakes and noncryptographic FNV-1a-64 hashes of valid
bus payloads (16 little-endian 32-bit words). FNV is a useful additional check,
not a collision-resistant integrity or numerical correctness proof. Timings
and output paths are excluded from all deterministic inputs. Raw event files
are local diagnostic inputs; the orchestrator may publish only their hashes and
compact counters.

## Small local verification

```sh
python3 tools/attention_profile/test_profile.py -v
```

These tests verify frozen-source hashes and byte identity, exact reversible
instrumentation, malformed-bound rejection, compile the complete original driver
against an explicit tiny test stub, verify the exact prefix/exception behavior,
verify a killed run retains only an unaccepted partial report, and show that
changing eval wall time does not change deterministic events. A separate small
synthetic physical AXI read/write exercise compares original and instrumented
headers: eval count, seeded backpressure state, beats, ACKs, drain state, and the
actual single memory store must match. They exercise successful read responses
and physical writes committed before the B-ACK callback. No local test here
builds or runs full production RTL, or provides numerical acceptance.

## Same-ELF eval-thread hotspot diagnostic

The GQA simulator boundary tested at `8a937ead` is rejected: it increased
mean eval time from 87.1451 to 148.8331 seconds for the same 4096-cycle prefix.
The source-pinned negative result is recorded in the Chinese execution report.
The default isolated workflow now builds only the original baseline once.
`--hotspot-sampling` and `--gqa-boundary-ab` are mutually exclusive; the latter
is retained solely as the reproducible historical experiment.

The two prefixes use the same ELF, fresh fixture, exact original generated SV,
and strict FP flags. Prefix 0 disables sampling; prefix 1 enables a Linux x86-64
thread-CPU timer directed at the thread calling `eval()`. Only an active eval
window records instruction pointers in a bounded signal-safe buffer. Other
threads are not profiled; this is not a whole-process call graph or hardware
performance-counter measurement. The two semantic/event/stdout digests must
match. `eval_ns` includes Window construction/destruction and signal-handler CPU
time as well as `d.eval()`. Off/on timing ratios are diagnostic observations,
not uninstrumented eval performance or a speedup.

Offline symbolization checks the actual ELF, load bias and symbol bounds, and
reports sampled function counts, relative offsets, unresolved counts and
generated C++ identities/sizes. Per-sample RIP sequences and ASLR addresses stay local. Compact summaries
may include at most five short, address-stripped assembly windows of at most
ten instructions each, alongside function counts and source identities. The unchanged 6000-second
build cap, 240-second prefix cap and 7800-second overall cap apply. This job
does not execute or accept a complete block; numerical acceptance remains false.
