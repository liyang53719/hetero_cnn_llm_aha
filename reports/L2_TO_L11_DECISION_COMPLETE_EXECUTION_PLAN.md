# L2-to-L11 decision-complete execution plan

Status: approved 2026-08-26. This document is subordinate only to
`ARCHITECTURE_AND_EXECUTION_PLAN.md` for canonical L0-L11 stage names and
freezes all choices needed for autonomous implementation from the current L2
state.

## Frozen contracts

- Keep the 128-bit command encoding. Upgrade descriptor schema to v2; unused
  roots are `0xFFFFFF`, while index zero remains valid.
- Each root chain has at most 16 records. Matrix may cache src0/src1/dst/bias,
  at most 64 records total. All referenced records are fetched, snapshotted and
  validated before the first CUSTOM_3 issue. Read-only cross-root alias is
  legal; unknown/duplicate/reserved-nonzero records are illegal.
- Common descriptor subtype/flags are zero in v2. Tensor ID is root index low
  12 bits; runtime forbids in-flight collisions. Stream tag is
  `{event_signal[11:0], stream_role[3:0]}` with roles primary/K=0,
  secondary/V=1, bias=2 and scale=3.
- Root roles are fixed by opcode: Matrix A/B/C; DMA source/policy/destination;
  SFU primary+program/optional-secondary/output; KV append K/V/metadata;
  gather metadata/NULL/output; share source/NULL/destination; alloc/free
  target/NULL/NULL; barrier event-list/NULL/NULL.
- Add record `0x12 matrix_aux` with bias index, activation, full/low output,
  repeating bias, Conv transform flags, depthwise, Gemmini spad IDs,
  max-pixels-per-row, asymmetric bottom/right padding and subarray mask.
  Subarray mask zero is illegal. L2 Conv requires no-pool; pooling belongs to
  L4 SFU.
- Add `0x50 dma_policy` with burst, outstanding, QoS, unaligned, coalesce and
  ordering controls. Add chained `0x60 event_list4`, up to 64 barrier events.
- Matrix dataflow is explicit OS=0 or WS=1. Quant modes 0..6 are none, W8
  per-tensor/per-channel, W4-storage G64/G128, native-W4 G64/G128. Completion
  statuses 0..10 are OK, illegal command, malformed chain, fetch error,
  unsupported policy, range/resource overflow, timeout, macro/protocol error,
  KV OOM, stale generation and KV invariant failure.

## Execution gates

1. `contract/descriptor-v2`: schema, Python typed packers, command root
   validation, example migration, committed expected-vector generator and all
   contract tests.
2. `l2/multi-op-sequencer`: production multi-tile OS, LOOP_WS, 1x1/3x3 Conv,
   optional bias and output requant/ReLU; ReLU6 is a following SFU operation
   because pinned Gemmini code 2 means LayerNorm. Use exact Gemmini tiling and no
   locally invented address policy.
3. `gate/L2-pass`: same retained RocketTile official-vs-descriptor command,
   write, busy, event and numerical equivalence; AHA baseline remains clean.
4. `l3/production-fabric`: four logical reads to physical 2R and two logical
   writes to 1W; bank-group round-robin, descriptor promotion after 8 wait
   cycles, response ownership, four direct streams, depth-16 command and
   completion queues, real-SRAM event scoreboard and diagnostic watchdog.
5. `gate/L3-pass`: at least 100000 integrated command/event/descriptor/DMA/
   stream transactions with no loss, duplication, reorder, starvation,
   assertion or timeout.
6. L4 CNN: torchvision 0.24.1 ResNet50/MobileNetV2 V2 weights; production SFU
   is logical 4x4/16 tiles and 16 Lake SRAMs. The existing 4x16 Garnet remains
   an immutable upstream baseline only.
7. L5 BF16: independent 16x32 BF16/FP32 array and Qwen2-1.5B-Instruct revision
   `ba1cf1846d7df0a0591d6c00649f57e798519da8`; q128/q384 and decode
   128/1024/4096 with per-node traces and no score-matrix writeback.
8. L6 W8/W4-storage, L7 advanced paged KV, L8 native W4 dual-dot, then L9
   one-layer real-weight and four-layer executable integrated model closure.
9. L10 readiness may continue, but strict L10 waits for official SRAM `.db`
   and LEF. DP mappings are 2x2048x64 and 4x4096x32. No black-box or handmade
   timing model may close L10.
10. L11 uses fixed A/B/C/D points, 1 GHz, 4 MiB, 100/40 GB/s and identical
    model/compiler/quantization. If no point meets every gate, report FAIL.

## Resource, evidence and recovery rules

- Every compile/test/generation/DC command is wrapped by `taskset -c 8-25`;
  Docker additionally uses `--cpuset-cpus=8-23`. Parallelism is at most j4.
- Start heavy work only with `MemAvailable > 10 GiB` and disk free >50 GB;
  simulations/synthesis use the 10 GiB capped runner.
- Long work records command, PID, cwd, affinity, start time and log, and uses
  blocking completion waits rather than periodic polling.
- Every gate updates `result.json`, `MASTER_LEDGER.json`, `NEXT_ACTION.json`
  and a <=200-line `HANDOFF.md`. Measured, cycle-accurate, analytical and
  post-synthesis data remain separately labeled.
- Commit and push each recoverable checkpoint. Never add the user's untracked
  AHA runtime preparation scripts. Do not mark a dependent stage PASS early.

## Immediate next action

Finish `contract/descriptor-v2`, run CPU-bound Python/spec/example regressions,
update the ledger and push the dedicated contract checkpoint before changing
the production RTL sequencer.
