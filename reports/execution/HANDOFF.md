# Local-agent handoff v6

State: L5.2 hierarchical DC revision 1 frozen, ready for production-lane
refactor. Four leaf DDCs pass; neither the flat compile nor leaf-only array
compile may be rerun.

## Closed locally

- L5.1 E1: 1,024 FP32 pipeline vectors; 132 Block128 vectors; 32 beats;
  random backpressure; zero mismatch/loss/dup/reorder.
- L5.1 E4 at CLN22UL 1.0 ns: Mul `+0.000160873 ns`, Add
  `+0.000159979 ns`, canonical Block128 `+0.0000136495 ns`; zero unmapped
  and unresolved.
- L5.2 E1: real 16x32/512-lane array, four contexts, 1,000,000 dependent
  steps in 1,000,000 issue cycles, 10,000 random-backpressure steps, numeric
  and tag/protocol PASS.
- L5.2 one-lane stage probe E4: WNS `+0.000159681 ns`, zero unmapped and
  unresolved. Diagnostic only.

## Still open

- Full 512-lane L5.2 E4 was stopped after 9,611 seconds in Mapping
  Optimization Phase 2. No final WNS, area, unmapped, or unresolved result.
- `work/results/l5_matrix_context_array/dc/status.txt` is stale from the
  pre-pipeline design (`-1.35148 ns`) and must not be used.
- L5.2 is not PASS.

## Implementation boundary

- Production FMA stages: HardFloat preMul, 24x24+48, postMul, round.
- Feedback latency is four cycles, matching four-context II=1.
- Generated RTL SHA256:
  `d36c11122854248d01bcf4c5c8bc6f07d9517127b34f6c1b7c6d65e89c193268`.
- Generated RTL was not hand edited; upstream status is clean.
- User runtime scripts remain untracked and must not be committed.

## v6 sandbox prerequisites

Archspec collateral, Qwen3.8 full-shape program/mock partition, and Sequence
Memory cycle E0 are retained from v6. They are not RTL E1/E3/E4 evidence.

## Next execution

Follow `reports/L5_2_HIERARCHICAL_DC_EXECUTION_PLAN.md`: map each generated
stage once, map one production lane containing its four data-register stages,
reuse that lane 512 times in the fixed 16x32 array, then compile only the
four-context wrapper. Revised array and full-top runs are capped at 20 and 30
minutes. Do not reduce array size/frequency or add false/multicycle paths.
