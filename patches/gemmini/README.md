# Gemmini integration/patch policy

No Gemmini source is included here. Apply changes only after the unmodified Chipyard/Gemmini baseline passes and its generated RTL is hashed.

Order:

1. External descriptor/command/event wrapper; no upstream edit.
2. Standalone memory adapter while preserving load/execute/store controllers and ROB.
3. Parameter-only 32×32 or multi-array cluster experiment.
4. BF16 operand + FP32 accumulation with explicit PE latency.
5. W4 storage unpack/dequant in load path.
6. GEMV subarray partition and direct Matrix↔SFU/KV streams.
7. Native W4 dual-dot only as a separately measured patch.
8. Native rectangular 32×64 only after auditing all `DIM` assumptions.

Every patch directory must contain `metadata.yaml`, `*.patch`, upstream commit, regression commands, numerical results and DC comparison.
