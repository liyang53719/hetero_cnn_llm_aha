# L5.2 hierarchical DC execution plan

## 1. Objective and retained evidence

Close the production `16x32` / 512-lane, four-context BF16 Matrix E4 gate at
CLN22UL 1 GHz without changing the RTL-visible geometry or numerical contract.

Retained evidence at commit `f632f35`:

- L5.1 is locally PASS at E1/E4.
- L5.2 real RTL E1 is PASS for 1,000,000 dependent steps, four-context II=1,
  10,000 random-backpressure steps, and all 512 lanes.
- The exact four BF16 stage boundaries pass the one-lane CLN22UL 1 GHz probe
  with WNS `+0.000159681 ns` and zero unmapped/unresolved references.
- The full flat compile was interrupted after 9,611 seconds and has no final
  timing result.

The interrupted DC log proves the runtime root cause:

- initial leaf-cell count: 903,987;
- DC reported `Uniquified 512 instances` for each of
  `HeteroBF16FmaPre`, `HeteroBF16FmaMul`, `HeteroBF16FmaPost`, and
  `HeteroBF16FmaRound`, followed by their HardFloat children;
- the run was still in Mapping Optimization after more than 2.5 hours.

Therefore the next flow must map each identical reference once and reuse the
mapped DDC. Re-running the previous full-filelist `compile_ultra` is forbidden.

## 2. Fixed resource and timing contract

- Every generate/compile/test/DC command is wrapped by
  `scripts/run_memory_capped.sh`, hence CPU affinity is 8-23.
- DC uses at most 8 cores; simulation uses at most 4 threads.
- Admission requires `MemAvailable > 10 GiB`.
- `MemoryHigh=24G`, `MemoryMax=30G`; free disk must exceed 50 GiB.
- Standard cell DB is the existing CLN22UL base-SVT typical/max, 0.8 V, 25 C.
- Clock period is 1.0 ns, uncertainty 0.08 ns, input/output budget 0.10 ns,
  output load 0.02.
- No false path on synchronous data, no multicycle exception, no reduced
  frequency, no reduced lane count, and no replacement analytical model.
- Generated SystemVerilog is emitter output and is never hand edited.

Runtime ceilings use one blocking command with `timeout`; there is no polling
loop. A timeout records `BLOCKED_RUNTIME` and the same command is not retried.

## 3. Phase H0: provenance and source checks

1. Regenerate `HeteroAllPrimitives.sv` from the committed Scala emitters.
2. Require empty upstream status and record generator/generated RTL SHA256.
3. Run Verilator lint/source checks for the existing production array.
4. Confirm the generated modules and exact interfaces:
   `HeteroBF16FmaPre`, `HeteroBF16FmaMul`, `HeteroBF16FmaPost`, and
   `HeteroBF16FmaRound`.

No RTL change is expected in H0.

## 4. Phase H1: map each HardFloat leaf once

Compile the four generated stage tops independently. Each combinational top
uses a 1.0 ns virtual clock with the fixed I/O budgets. Outputs are ignored
under `work/generated/l5_matrix_hier_dc/`:

1. `HeteroBF16FmaPre.ddc`;
2. `HeteroBF16FmaMul.ddc`;
3. `HeteroBF16FmaPost.ddc`;
4. `HeteroBF16FmaRound.ddc`.

For each leaf save status, timing, area, check-design, reference list, tool
version, elapsed time, command, and DDC SHA256. Acceptance is WNS >= 0,
zero unmapped, zero unresolved, and no latch/loop. Normal `compile_ultra` is
used first. One high-effort retry is allowed only for the failing leaf and is
capped at 10 minutes.

Any leaf failure stops H2; execution does not weaken constraints.

## 5. Phase H2: fixed 16x32 array hierarchy

1. Read the four mapped leaf DDCs.
2. Analyze only `rtl/matrix/bf16_outer_product_array.sv`.
3. Elaborate with `ROWS=>16,COLS=>32`; require the specialized design name
   `bf16_outer_product_array_ROWS16_COLS32`.
4. Disable boundary optimization and constant propagation across each mapped
   leaf boundary; set the mapped leaf designs `dont_touch`.
5. Compile only array registers, valid/ready control, flag reduction, and
   interconnect with `compile_ultra -no_autoungroup` at normal effort.
6. Cap wall time at 45 minutes.

H2 acceptance:

- WNS >= 0 at 1.0 ns;
- zero unmapped/unresolved, latch, and combinational loop;
- the log contains no `Uniquified 512 instances of design
  'HeteroBF16Fma...` message;
- one mapped design exists per stage reference while `report_reference`
  records 512 physical instances per stage;
- mapped area includes all 512 lanes;
- mapped array DDC and reports are written and hashed.

If the parameterized DDC name does not link exactly, stop with
`BLOCKED_HIERARCHY_NAME`. Do not silently black-box or substitute a smaller
wrapper. A fixed 16x32 wrapper may be added only as a handwritten RTL change,
followed by the complete E1 regression.

## 6. Phase H3: four-context full top

1. Read the accepted mapped array DDC.
2. Analyze only `rtl/matrix/bf16_outer_product_context_array.sv`.
3. Elaborate the default production parameters and prove that instance
   `array` resolves to the specialized mapped 16x32 design.
4. Disable boundary optimization and set the array instance/design
   `dont_touch`.
5. Compile only context banks, FIFO, completion/busy control, accumulator
   selection, and top-level I/O logic at normal effort.
6. Cap wall time at 30 minutes.

H3 is the formal L5.2 E4 evidence and must report:

- final WNS/TNS and top five setup paths;
- cell area/count including the reused mapped array hierarchy;
- zero unmapped and zero unresolved references;
- zero inferred latches and combinational loops;
- expected one array macro-hierarchy instance and 512 lane-stage instances;
- no stale status file reuse.

If a failing path is confined to wrapper counters or non-feedback control,
pipeline that control without changing completion semantics. If the failing
path is the accumulator feedback loop and requires latency greater than four
cycles, stop with `BLOCKED_DECISION`; do not add a fifth context or falsify
four-context II=1.

## 7. Phase H4: functional revalidation and closeout

After any synthesis-script-only change, regenerate RTL and rerun the existing
full L5.2 E1 anyway:

- 1,000,000 dependent steps;
- issue window exactly 1,000,000 cycles;
- four contexts and 512 lanes;
- 10,000 random-backpressure steps;
- exact numeric/tag/last/counter/protocol checks.

Run canonical v6 sandbox validation. Then atomically update:

- `reports/execution/l5_matrix_context_local_e1_e4_result.json`;
- `reports/execution/MASTER_LEDGER.json`;
- `reports/execution/NEXT_ACTION.json`;
- `reports/execution/HANDOFF.md` (maximum 200 lines);
- `config/control_plane.json`, `local_agent/stages.yaml`, and final validation.

L5.2 closes only when H3 and H4 both PASS. Push the closeout commit, enter
`WAIT_REMOTE_AUDIT`, and send the user a Feishu notification. If any formal
gate remains open, push only an explicitly requested checkpoint and do not
send a completion notification.
