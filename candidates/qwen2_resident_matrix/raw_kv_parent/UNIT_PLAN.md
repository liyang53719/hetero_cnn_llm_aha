# Bounded actual-parent unit

## 中文计划

- 已完成：父级 11 项控制测试加 16 项准备检查，普通 Python 与 -O 各通过 27 项；零 fuzz 组合和 13 个固定 Scala 编译单元/原始源码切片校验通过。
- 已完成：复用的进程组超时/SIGTERM 清理 3 项测试通过。
- 已完成：首次 CI 的 Scala 编译、两个配置的展开与存储结构检查。RTL 测试阶段在 240 秒后超时，尚无父级场景通过证明。
- 待办：审核新增的无载荷进度标记和构建计数，再以相同预算诊断超时；尚未启动第二次运行。

The first actual run passed parent Scala compilation, elaboration and both
structural audits, then timed out in the 240-second RTL test stage. No parent
scenario completion is established. Diagnostic revision 2 is prepared for a
same-budget run; publication of the workflow comment activates that run.

## Real implementation and dependency closure

The DUT is TransposedDenseDownOwner, instantiated directly with burst writes,
FFN tiles/window/drain, K-window and Dense drain enabled. Only enableRawKv varies.
There is no replacement parent, new kernel, Matrix implementation, HardFloat
arithmetic, DMA RTL, full block, performance experiment, or forced register.

prepare_unit.py first runs the published parent composition gate. It compiles
all three original composed parent/bank/IO files. Protocol.scala and
MatrixAccumulatorSeedProtocol.scala are exact full sources. BurstProtocol.scala
receives the existing combined_service and service_seed patch sections.

Seven exact source slices supply NumericPolicy, OwnerKind, OwnerJob,
OwnerResult, QwenBlockShape (including companion), DenseCycleProfile and F32.
Only the first two existing official-policy patch hunks affect policy/job
before extraction. The current unrelated QwenRmsBorrowerControl declaration and
QwenOwnerKernel body are not needed. Slice boundaries must occur exactly once.
No protocol widths or F32 operators are rewritten. Full input Git blobs,
extracted slice SHA256 and all 13 generated Scala units are pinned. The support
declarations and BurstProtocol were independently compared byte-for-byte with
the existing full 72-source composition. This is source evidence only.

## Two simulator builds, four required scenarios

1. default_off_dense: M16 K32 N32 ordinary Dense completes with no raw interface.
2. enabled_dense_drain: M16 K256 N32 splitK128 drives original A/B SRAM loading,
   operand backpressure, opaque Matrix group/step/result service, actual prefix
   writes and ACKs, prefix reads/seed begin/256 beats/ACK, final output writes,
   held completion and its retirement edge before raw acquisition.
3. retained_a_window: a real successful M16 K32 N32 window produces a tile;
   all 32 tile reads complete and the tile releases. Retained A still blocks raw
   acquisition. Existing invalidateLease must be accepted on a prior edge.
4. raw_fault_retirement: raw write/read response holding and early release,
   foreign parent response and backend abort, matching raw ACK and release;
   borrower softReset cannot repair the poisoned original backend.

The three enabled scenarios share one simulator instance and perform no cold
reset between them. All accepted service debt and held responses must retire
at scenario boundaries. Four distinct completion markers and exactly two
passing ScalaTest cases are required. Synthetic service data is deterministic
finite routing tokens, not an arithmetic oracle or real model tensors. Tests
check accepted groups/steps/results, prefix and output ACK bytes, seed data,
raw bits and ownership. They do not establish numeric inference correctness,
128-token prefill execution, hardware throughput, or RTL/Python cycle equality.

## Bounds, resources and artifacts

Tool versions reuse the successful bank-unit setup: Java17, sbt1.10.2,
Scala2.13.16, Chisel6.7.0/plugin, chiseltest6.0.0, ScalaTest3.2.19; Verilator from
Ubuntu24.04 apt. Maven sources and pinned known-jar lock are unchanged. Resolved
compiler/plugin/test/transitive jar hashes are recorded; jars absent from the
existing lock are disclosed, not represented as pre-pinned. All resolved jars
are frozen and rechecked before later stages and at completion.

Single workflow attempt,12-minute job ceiling. Runner total600 seconds with
120 dependency/120 compile/60 elaboration/240 RTL stage caps. Timeout/SIGTERM
uses the existing process-group TERM then KILL cleanup. No automatic rerun.
Preparation/model tests precede the runner. Optional manual dispatch exists;
push triggers only .github/workflows/raw-kv-parent-unit.yml on main.

CHIRRTL audits require the actual owner, its bank module and one original
operand Queue only: sixteen1376×256 A SRAMs, sixteen160×256 B SRAMs, each1R1W,
and the existing depth4,4359-bit MatrixStreamStep queue. No extra memory,
Matrix arithmetic module or external black box is accepted. These are emitted
structure checks, not synthesis area or timing. Raw optional ports must be
absent/present in both owner and banks for raw-off/on.

Before dependency resolution, freeze full source inputs, source slices,
generated compile units, test/runner/preparer/pins, Maven lock, build.sbt,
build.properties and workflow bytes. Recheck between stages and after RTL.
On failure only, up to 4096 UTF-8 bytes of selected compiler/test diagnostics
are sanitized into the existing summary and CI output. Absolute paths, token
patterns, source echoes and bulk payload lines are removed or redacted; full
logs are not uploaded. Negative tests check this failure path.
Only four small evidence files upload: summary.json, source-sha256.json,
dependency-sha256.json and rtl-sha256.json. No raw tensors, weights, payload
traces, full RTL, simulator logs or private execution metadata upload.

Preparation only:

```
python -m unittest candidates.qwen2_resident_matrix.raw_kv_parent.test_model candidates.qwen2_resident_matrix.raw_kv_parent.test_unit_prepare
python -O -m unittest candidates.qwen2_resident_matrix.raw_kv_parent.test_model candidates.qwen2_resident_matrix.raw_kv_parent.test_unit_prepare
python -m candidates.qwen2_resident_matrix.raw_kv_parent.prepare_unit
```

Explicit execution (compiles and runs RTL):

```
python candidates/qwen2_resident_matrix/raw_kv_parent/run_unit.py --out /tmp/raw-kv-parent-unit
```


## First actual parent run and diagnostic revision

Run 38869042244 compiled the exact closure (26.71 s) and elaborated both
raw-off/raw-on parent configurations (9.09 s). Both existing-memory audits
passed. The parent RTL stage timed out at its unchanged 240 s limit; total
runner time was 303.21 s. Only raw-off test SystemVerilog was captured
(SHA256 69e1ad91a476df33a308c1aba3570dcd207c786868067dedc5579936b0606111).
This does not establish simulator startup or a completed parent scenario.
The prior failure receipt had no selected error lines and could not separate
C++ compilation from clock-driving runtime.

Diagnostic revision 2 adds fixed case-start, simulator-ready, scenario and
1024-cycle markers; the summary accepts only known marker names and bounded
integer counters from bounded log windows. It also records counts of C++
files, object files and the known simulator executable in the two known test
case directories. No build contents, arbitrary paths or payloads are retained.
A case-start without simulator-ready means lowering/build/startup, not proof
that C++ compilation itself is the bottleneck. Counts provide further bounded
evidence; absent executable counts alone are not proof of a failed build.
Budgets, toolchain, original DUT, all scenarios and stimuli remain unchanged.
The workflow comment activates one reviewed diagnostic run when published;
no second run has been launched as part of preparing these edits.
