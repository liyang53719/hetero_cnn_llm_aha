# Three-model q1024 performance evidence recovery

Baseline: main bc8bbc3. Status: ACTIVE, not full-network performance PASS.

## Frozen measurement contract

- Batch 1, 1024 input tokens, all text decoder layers, final norm and last-token
  LM head. No MTP speculative branches or vision work in the base prefill metric.
- One shared authoritative RTL generation, 800 MHz / 1.25 ns, BF16 Matrix
  16x32 with five accumulator contexts: 512 MAC/cycle = 409.6 GMAC/s.
- Wall time includes descriptor, DDR 100/40 GB/s, KV/state traffic, queues,
  padding and stalls. Report useful MACs separately from executed/padded MACs.
- useful wall utilization = useful Matrix MACs / (512 * request wall cycles).
  Array issue utilization and SFU/state work are separate metrics.
- Missing full-request RTL counters remain null, not zero and not inferred from
  root canaries or multiplied one-layer/service-curve cycles.
- Existing operator/DC acceptance is component evidence; its synthetic-memory
  canaries and disconnected SRAM PPA aggregate do not establish model throughput.

## Execution gates

1. P0: versioned evidence audit, source hashes, three-model analytical screening,
   historical 1GHz reports explicitly segregated. Freeze local model profiles;
   Qwen3.5 currently uses revision 62704185, not the older plan revision.
2. P1: add and test a shared full-request counter schema: RTL/source hashes,
   model revision, full shape/layers, start/end cycles, accepted/completed Matrix
   steps and lane masks, DDR read/write bytes, stall attribution, numerical proof.
   Reject synthetic constant-payload and incomplete-layer traces as measured PASS.
3. P2: replace canary's one zero Matrix step per phase with descriptor-driven
   complete tiling, real tensor memory continuity and bounded DDR response timing.
   Exercise small nonzero differential cases before full q1024. Fix canonical
   sources only; regenerate RTL. Reuse existing numerical datapaths.
4. P3: Qwen2 full request; then Qwen3.5 GDN/state/MoE and Qwen3.8 QSA/PLE/hyper
   full requests. Require owner trace, routing, output and cross-layer consistency.
5. P4: report q1024 cycles/token rate/utilization and bottleneck breakdown. Replay
   affected numerical and 1.25ns DC gates after source changes. Do not extrapolate
   current component DC into a new integrated design timing PASS.

## Decisions and resources

Qwen2 historical 300 token/s is a target, not an achieved 800MHz claim.
No automatic multi-cluster/W4 architectural expansion is authorized by this
measurement plan. If targets exceed compute lower bounds, present the design
choice before expanding hardware. Qwen3.8 figures are local-profile estimates.
All test/generation/DC: CPU8-23, one heavy task, j4 Verilator/DC8,
MemoryHigh24G/Max30G, available>10GiB, disk>50GiB, timeout600s. Blocking waits.
Update short handoff and commit/push each recoverable checkpoint on main.
