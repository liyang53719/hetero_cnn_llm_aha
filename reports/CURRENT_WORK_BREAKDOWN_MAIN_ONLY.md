# Current work breakdown on consolidated main

## Closed and accepted

- L0-L3 control/upstream/wrapper/shared-fabric baselines.
- L5.1 Block128 component E1/E4, with effectively zero timing margin.
- L5.2 Revision8B-B 512-lane, five-stage/five-context Matrix E1/H3.
- L5.3 Controller and Block32-weight component E1/E4; the trace bridge is accepted only as non-single-simulation evidence.
- L5.4 one- and two-lane fused-SiLU standalone E1/E4 candidates.

## Current local-agent critical path

1. Build one integrated q128 QK -> Block32/Block128 M/L/O -> PV simulation using the deterministic vector pack.
2. Extend to q384 and reviewed q1024 rows, exactly 43,008 merges and random backpressure.
3. Freeze SiLU edge behavior, measure Matrix-producer stall and select one/two lanes.
4. Execute the 11-case integrated E3 matrix.
5. Run 28-layer q1024 >=300 token/s within SRAM and DDR limits.

## Sandbox v7.0 completed

- Attention pack: 1,536/180/108 q128/q384/q1024 rows, max error `1.0728836059570312e-06`.
- SiLU: 625 special vectors and 160 stall scenarios; two edge policies require review.
- Quant: 8,192 arbitrary K-tail schedules plus source-ready sequencer RTL.
- State: 5,000 adversarial transactions, generation wrap and zero page leak.
- E3: 11 coverage-driven cases and mandatory counter contract.

## Other local dependencies

CNN/AHA E1/E4; pinned llama.cpp parity and quant RTL/PPA; production state RTL/iDMA E3; official Qwen3.5/Qwen3.8 backends; real llama.cpp/GGUF; SRAM/post-route/PVT/SAIF and final Archspec promotion.
