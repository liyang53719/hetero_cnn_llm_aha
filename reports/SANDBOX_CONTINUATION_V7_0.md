# Sandbox continuation v7.0

This increment advances work that does not require Verilator/VCS, CLN22UL, iDMA/DDR, official weights or llama.cpp linkage.

## Completed in sandbox

- Deterministic Attention E2 pack: q128 full 1,536 rows; q384 180 reviewed rows; q1024 108 reviewed rows; maximum absolute error `1.0728836059570312e-06`; q1024 merge rows `43,008`.
- Fused-SiLU edge and burst envelope: 625 special vectors and 160 producer/consumer scenarios. Two edge-policy gaps are recorded for local review.
- Quant K-tail scheduling: 8,192 FP16/Q8_0/Q6_K/Q3_K cases, shared 16-value beat contract and source-ready sequencer RTL.
- Sequence-state adversarial vectors: 5,000 transactions covering duplicate/stale/missing acknowledgements, OOM rollback, generation wrap and zero page leak.
- L5.5 minimum E3 matrix: 11 coverage-driven cases, including baseline, review scenario and the closest analytical pass/fail around 300 token/s.

## Evidence boundary

These are deterministic E0/vector/source contracts. They do not replace the open full Attention single-simulation E2, measured SiLU lane selection, integrated iDMA/DDR E3, quant/state RTL E1, or post-route signoff.
