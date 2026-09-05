# Current handoff: three-model q1024 performance recovery

- Goal ACTIVE; plan reports/THREE_MODEL_Q1024_PERFORMANCE_PLAN.md.
- main only; full-model q1024 measured models still0/3.
- No generated RTL hand edits. Preserve two excluded user runtime scripts.
- CPU8-23, one heavy task, Verilator j4/DC8; MemoryHigh24G/Max30G,
  MemAvailable>10GiB, disk>50GiB; commands<=600s, blocking waits.

## Current result

- FULL q1024 layer0 K projection numerical PASS:262144 BF16 outputs exact,
  4272278 ROI cycles,402653184 useful MACs,18.4078% utilization of512 MAC/cycle.
- At nominal800MHz:5.3403475ms for this operator only. No full-model token/s claim.
- Report Q1024_CONTINUOUS_K_RESULT.json validates six sequential receipts,
  immutable binary/data, checkpoint hashes and restored-cycle continuity.
- Final receipt work/results/q1024_continuous/p1/segment_005.json.
- FULL q1024 layer0 V also PASS:262144 BF16 outputs,4272278cycles,
  402653184 usefulMACs,18.4078% utilization. Q1024_CONTINUOUS_V_RESULT.json.
- Q segments0/1 checkpointed at2399993cycles/439296 completed Matrix steps;
  not numerically complete. No simulation running at handoff.
- Q resume recipe runs2ms per segment (observed284.41 host CPU seconds), with
  unchanged600s timeout; K/V scripts remain unchanged. Freeze the new Q recipe too.
- Only layer0 norm inputs/weights preloaded; no L2/output injection.
- Fixtures reproduce true1024-token ordering via exact token-ID golden reuse for
  position-independent layer0 norm/raw projections. Never use for RoPE/attention/later layers.

## Recovery contract

- VCS debug_access+r; preserve simv_group8_checkpoint and its libraries.
- Preserve .chk + .chk.FILES + .chk.ucli. Never push snapshots (process data).
- VCS clears ucliCore::_vars_list on restore. Refresh UI baseline before save;
  control is reloaded from locked external file, not restored environment.
- Small chained235-state test and actual K checkpoints validated this workaround.
- Original segment1 failure retained; successful retry is segment_001_attempt1.chk.
- Do not edit saved Tcl recipes; original initial recipe hash24ea0b46 is retained.
- Runner --retry-failed is explicit, rejects live PIDs, keeps failed files.

## Next action

taskset -c 8-23 python3 scripts/run_q1024_projection_segment.py --projection 0 --segment 2

Continue Q until actual PROJECTION_NUMERICAL_COMPLETE, then run
scripts/collect_q1024_projection_chain.py --projection 0 under CPU8-23.
Do not regenerate fixtures or rebuild simulator.
After projections: remaining decoder/28layers, Qwen3.5/3.8 and current DC/PPA
are still open. 100/40GBps model is a bandwidth ceiling, not DRAM latency calibration.
- Project work/models currently contains Qwen2 weights only. User was asked
  asynchronously for a Qwen3.8 checkpoint/reference location; no answer yet.
