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

Revision 1 evidence: mapping only the four combinational leaves removed the
`Uniquified 512` messages, but the array compile still entered global
optimization with 2,773,602 expanded leaf cells and 167,497 sequential cells.
It reached the fixed 45-minute limit and was stopped after 2,731 seconds.
Therefore the four stage-local register banks must also move below a reusable
production lane boundary; the leaf-only array command must not be retried.

Revision 2 evidence: the production-lane refactor preserved the complete E1
gate and its mapped lane passed at WNS `+0.0135558 ns`. A 512-lane array using
one preserved lane design still timed out after 1,230 seconds because
`compile_ultra` entered global delay optimization over 2,929,236 expanded leaf
cells and 153,156 sequential cells. There was no lane uniquification. The
remaining issue is the compile command, not hierarchy correctness.

DC X-2025.06-SP3 documents that `compile -incremental_mapping` exempts already
mapped portions from logic-level optimization. H2 revision 2 therefore uses
incremental mapping for only the unmapped array glue; `compile_ultra` is
forbidden for H2 and H3.

Revision 3 evidence: incremental mapping still expanded 2,929,236 leaf cells
and 153,156 sequential cells for implementation selection and reached the
10-minute limit after 631 seconds. The top must contain no unmapped glue before
hierarchical composition. Revision 3 therefore maps array control and wide
glue as separate real DDCs, then performs link/report/write only at array top.
This is not a black-box flow: lane, control, broadcast, reduction, and their
leaf implementations are all mapped and retained for hierarchical timing and
area accounting.

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

## 5. Phase H1.5: map one production lane pipeline

Create `bf16_fma_pipeline_lane`, a handwritten internal hierarchy containing
exactly one Pre/Mul/Post/Round chain and the same four data-register enables
already controlled globally by the array. It has no command, context, or
numerical policy of its own. The array retains the four global valid bits,
ready chain, counters, and flag reduction, and instantiates 512 identical lane
pipelines.

The refactor must preserve:

- the public array and context-wrapper ports;
- four-cycle FMA feedback latency;
- four-context II=1;
- the exact generated HardFloat stages and RNE/exception semantics;
- one physical 16x32 / 512-lane array.

Map the lane once after reading the four accepted leaf DDCs. Disable boundary
optimization for all generated leaf designs and write one mapped lane DDC.
Runtime is capped at 10 minutes. Acceptance is WNS >= 0, zero
unmapped/unresolved, one design variant per generated stage, and exactly one
instance of each stage inside the lane.

Because H1.5 changes handwritten RTL hierarchy, rerun the complete million-step
E1 before any array E4 claim.

## 6. Phase H1.6: map array control and wide glue

Move the existing global valid/ready pipeline and counters into
`bf16_outer_product_array_control`. Move the four 512-way write-enable nets,
512-way asynchronous reset distribution, and 512-lane flag OR reduction into
one fixed `bf16_outer_product_array_glue512` module. These are implementation
hierarchies only; they add no cycle and expose no public port.

Map control and glue independently at the same 1.0 ns/I/O contract and write
real DDCs. Each run is capped at 10 minutes and must pass WNS, mapping, link,
latch, and loop checks. The complete million-step E1 is rerun after this RTL
refactor.

## 7. Phase H2: fixed 16x32 array hierarchy

1. Read the accepted lane, control, and glue DDCs.
2. Analyze only `rtl/matrix/bf16_outer_product_array.sv`.
3. Elaborate with `ROWS=>16,COLS=>32`; require the specialized design name
   `bf16_outer_product_array_ROWS16_COLS32`.
4. Disable boundary optimization and set all three mapped designs
   `dont_touch`.
5. Prove the specialized array contains only mapped lane/control/glue
   references and connectivity. Do not invoke `compile` or `compile_ultra`.
6. Link, report full hierarchical timing/area/references, check mapping and
   unresolved references, and write the array DDC. Cap wall time at 10 minutes.
   All superseded array compile commands are evidence, not retry paths.

H2 acceptance:

- WNS >= 0 at 1.0 ns;
- zero unmapped/unresolved, latch, and combinational loop;
- the log contains no `Uniquified 512 instances of design
  'bf16_fma_pipeline_lane'` message;
- one mapped lane design exists while `report_reference` records 512 physical
  lane instances;
- mapped area includes all 512 lanes;
- mapped array DDC and reports are written and hashed.

If the parameterized DDC name does not link exactly, stop with
`BLOCKED_HIERARCHY_NAME`. Do not silently black-box or substitute a smaller
wrapper. A fixed 16x32 wrapper may be added only as a handwritten RTL change,
followed by the complete E1 regression.

## 8. Phase H3: four-context full top

1. Read the accepted mapped array DDC.
2. Analyze only `rtl/matrix/bf16_outer_product_context_array.sv`.
3. Elaborate the default production parameters and prove that instance
   `array` resolves to the specialized mapped 16x32 design.
4. Disable boundary optimization and set the array instance/design
   `dont_touch`.
5. Compile only context banks, FIFO, completion/busy control, accumulator
   selection, and top-level I/O logic using the same incremental-mapping
   command; never globally optimize the accepted array DDC.
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

## 9. Phase H4: functional revalidation and closeout

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
