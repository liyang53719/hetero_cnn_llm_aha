# Sandbox continuation v6.6

Targeted execution performed without Verilator/VCS/DC/Formality:

```text
11 new Python tests PASS
Python compileall PASS
Blocked Attention numerical Golden PASS
Sequence Memory concurrency/MSHR model PASS
Qwen3.8 policy -> Command128 lowering PASS
```

## Blocked Attention

Maximum difference versus dense causal GQA:

```text
max_abs     2.384185791015625e-07
relative_L2 1.1367033572237338e-07
```

q1024 merge count remains 43,008; score and probability DDR materialization are
zero. The first real-stream RTL contract uses two-entry score and probability
FIFOs.

## Sequence Memory

The model demonstrates same-page MSHR coalescing, OOO device completion with
in-order retirement, stale-generation rejection and a bounded outstanding
window. First RTL point is frozen at 8 MSHRs and 16 data requests outstanding.

## Qwen3.8 lowering

```text
layers    48
segments  48
commands  1648
barriers  48
program   fe2e4fe210a7905e01bc7ed13c09d96cdbbc5642174e361535387b46adc09738
```

These are E0/source contracts, not real hardware or official-weight execution.
