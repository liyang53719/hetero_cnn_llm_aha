# Three-model operator closure handoff

- Branch: `main`; baseline: `b55ddcb`.
- Active plan: `reports/THREE_MODEL_CHISEL_RTL_DC_800MHZ_EXECUTION_PLAN.md`.
- Stage: `G0_CONTROL_PLANE_FREEZE`.
- State: `PLAN_LANDED_PENDING_LOCAL_SOURCE_REPLAY`.
- Implementation origin: Chisel; no Catapult HLS source/report exists in main.
- Frozen coverage: 18 model roots, 25 primitive modules, 58 terminal bindings.
- Models: Qwen2 30/30, Qwen3.5 93/93, Qwen3.8 150/150, plus Vision canary.
- Clock: 800 MHz / 1.250 ns, uncertainty 0.080 ns, I/O 0.100 ns.
- Library: CLN22UL base SVT TT 0.8 V 25 C.
- Resources: CPU 8-23, Java CPUs 8, Verilator j4, DC cores 8,
  MemoryHigh 24G, MemoryMax 30G, MemAvailable >10 GiB, one heavy task.
- Generated RTL must never be hand edited.
- Next: push this checkpoint, create Goal, then run G1 source replay.
