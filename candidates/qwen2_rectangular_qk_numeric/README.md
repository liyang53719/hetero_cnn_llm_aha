# Fixed actual-Matrix QK partial probe

This is a **real4096-MAC RTL** integration candidate, not the previous controlled
return probe. Frozen `QkRectangularProfile` connects to unchanged
`MatrixPipelineProbe` → `MatrixPipelineService` → eight retained512-MAC endpoints.
The actual four HardFloat ABI leaves are emitted with the wrapper. The driver
supplies operands and B acknowledgments, never Matrix results. A read-only tap
checks the same `result.fire` payload accepted by the profile.

## Three bounded tests, four subcases

1. Published signed-zero stimulus, five contexts × eight FMA steps:40 actual
   returns. Selected(0,0) must remain `0x80000000`, including every intermediate.
2. Published M17 tail stimulus, qbase16, one query row, stripeBase0, five
   partials × eight steps:40 returns and680 selected FP32 comparisons. Frozen
   `expected_tail.hpp` has exactly40×17 integer-FMA expected words. This is **one
   five-stripe group**, not all16 stripes or a completed dot/score. Padded rows,
   keys and disabled slices must produce the expected zero bits.
3. Published future-key Inf stimulus: qbase0 has16 valid rows and key16 is
   noncausal. One stripe, eight returns completes without poison. After reset,
   qbase16 selects that key; its first actual NaN return must poison, suppress
   B publication and drain the real service error terminal. Unselected NaNs
   are checked by IEEE classification, not a host-specific NaN payload oracle.

Exactly89 accepted wide steps,704 B-word write ACKs,375632 finite bit checks
(including return, write and B readback checks) and176 NaN-class checks are
required. Each case activates one32-column slice:45568 physical FMAs, while the
installed capacity is4096×89. The other seven endpoints remain instantiated;
zero outputs there are not active MAC work. A global20000 simulation-cycle
watchdog only bounds this fixture, not accelerator performance.

B is a fixed80-KiB **host testbench SRAM model**, one accepted32B write/ACK at a
time. ACKs follow real request acceptance and copy that exact payload to its
bank/word address. Every terminal write has13-cycle ACK delay; other writes
and request readiness also stall. Final completion requires all704 actual ACKs.
After checking B bytes, the host sends release. This is a test consumer replacing
the external ordered-fold contract; no production fold occurred. Real A gather,
B SRAM RTL/arbiter,16-stripe fold, BF16 dot/score, softmax, Host and DMA are outside
this test. No business data or whole-block performance conclusion is produced.

## Physical scope

The original five accumulator contexts total80KiB; retained lane result FIFOs
also total80KiB and preserve their readers. Matrix service retains its existing
32-KiB two-tile FIFO and eight metadata entries. The candidate capture is16KiB.
Nothing borrows result FIFO capacity. No A SRAM is instantiated in this isolated
probe; the fixture is a trusted operand supplier. B's80KiB is testbench storage,
not an additional synthesized SRAM. These scope distinctions remain after PASS.

## Fixed expectations and cold checks

The680 frozen words use the already-reviewed integer `arithmetic.fma` with
`j=context+16*step`, Q BF16=`0x3f00+j%7`, K BF16=`0x3e80+(key+j)%9`, initial+0.
`test_cold.py` regenerates every word and independently crosschecks libm.fmaf;
it also checks the frozen native final partials, signed zero and causal Inf.
A declared-port C++ stub checks syntax only and is never executed. It does not
prove generated ABI compatibility. Runner failure/timeout tests use real GNU
timeout and a measurement-wrapper stub because local GNU time is absent;
real execution requires `/usr/bin/time`. Synthetic failure, inner/outer timeout and
direct TERM and launch-window TERM cases verify exit receipts and termination of a TERM-resistant worker
and grandchild. Already terminated zombies are permitted; live descendants are
rejected after a bounded signal-delivery check. No cold check emits or simulates RTL.

```sh
python -m pytest -q candidates/qwen2_rectangular_qk_numeric/test_cold.py
python -O -m pytest -q candidates/qwen2_rectangular_qk_numeric/test_cold.py
```

## Real execution budget and provenance

`run_numeric.sh ABSOLUTE_NEW_OUTPUT` is **not run during preparation**. It uses
only original retained Matrix sources, the original hierarchy config and pinned
HardFloat commit `c1105e6ac6a0dd90fc80893efc4830ab609005d3`. The sole clock dependency
comes from official pulp-platform/tech_cells_generic commit
`3a3de73632a06826b1bd9c65a0a2e92b32016845`, `src/rtl/tc_clk.sv`, checked against
SHA256 `93e9747504fa1da6473560341febbfae6c5e917768633a84fc9ef12299293207`.
No full iDMA generation, Dense, SiLU or original multi-component runner is used.

Budget proposal:30 minutes including setup/receipts, with a1500-second runner
cap, at most two compiler jobs and3-GiB JVM heap. Scala compile180s + emit120s;
Verilator generation300s + hierarchical make600s; simulation60s. Every stage
also respects remaining runner time. Each stage tracks its GNU-timeout process
group. Signals during background launch are latched until its PID is captured.
TERM/INT/HUP forwards TERM, waits at most five seconds, kills residual
descendants and records failure before exit. Normal stage termination also kills
residual descendants; the stage timeout has a10-second kill grace. Interrupted
measurement is recorded as NA, never invented elapsed/RSS. Record elapsed and
GNU-time maximum child RSS;
that RSS is **not aggregate concurrent process-tree memory**. JVM heap and job
count likewise do not establish a total physical-memory bound. Failure/timeout
retains diagnostic receipts and does not trigger a larger automatic retry.

Historical evidence, not a prediction: tracked
`reports/execution/PRODUCTION_PIPELINE_REAL2_a3cb4a7307a6/components/compile_emit_silu.log`
records Scala31s and Matrix emit6s. Its final02:40:51 timestamp and the next
`tiny/compile_emit.log`02:44:04 timestamp enclose193s of the old serial workflow,
including two real component builds/simulations, error tests and transition.
This is a historical containing interval, not standalone Matrix wall time or
RSS. The prior controlled-return283s is not used to predict this run.

The inactive `workflow.yml.in` is a proposed new self-path-triggered job. Only
copy/publish it to the named workflow after source review and budget approval.
Keep production `chisel/**`, the frozen profile and existing workflows unchanged.
The new exact trigger path should match only that unit job and payload guard.
Only source/RTL hashes, stage timing and fixed-test summary text may be uploaded;
no binary fixtures, native helper reports, work tree or private metadata.
