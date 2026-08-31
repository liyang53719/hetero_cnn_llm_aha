# Sandbox continuation v6.9

## Audit correction

The user-reported local-agent commit `eba2462` is valid and closes L5.2, but it was not the branch HEAD when this audit began. `main` had already advanced to `c13b746...` through later sandbox-only fast-forward commits. There is one branch (`main`) and no divergent history.

## New L5.3 work

A bounded ready/valid controller was implemented for a single shared Matrix port alternating QK and PV, a two-entry score FIFO, a Block128 SFU command port and a two-entry probability FIFO. The executable protocol reference verified:

```text
q128   tasks 240,   merge rows 0
q384   tasks 1872,  merge rows 4608
q1024  tasks 12672, merge rows 43008
```

Nominal and randomized command/service stalls preserve completion order, FIFO bounds and zero score/probability DDR bytes. Four Python tests passed. RTL, Verilator TB, E1 script, DC filelist and DC script are source-ready.

## New L5.4 work

A bit-oriented implementation contract was built for the selected 128-entry FP16 direct-SiLU table. The source-ready RTL performs:

```text
BF16 gate -> Q4.12 range/index frontend
FP16 ROM y0/y1 -> FP32 conversion
(y1-y0)*fraction + y0
fused multiply by BF16 up input
FP32 -> BF16 RNE
```

All floating add/multiply operations use the existing generated elastic FP32 pipelines. Metadata travels through bounded FIFOs, preserving tag/last and exception flags. One- and two-lane lock-step wrappers, vectors, TB and DC/E1 scripts are included.

200,000 random fused cases passed:

```text
mean absolute error  0.000326079
relative L2 error    0.000863007
RMSE                 0.00181124
max absolute error   0.125
```

## Sandbox evidence boundary

Executed here:

```text
Python tests             8 PASS
Python compileall        PASS
Attention protocol E0    PASS
SiLU bit contract E0     PASS
RTL/TB delimiter checks  PASS
Shell syntax             PASS
```

Not executed here:

```text
SystemVerilog elaboration
Verilator/VCS E1
generated HardFloat build
CLN22UL DC/PPA
full Attention numerical E2
integrated E3
```
