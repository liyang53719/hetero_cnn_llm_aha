# Sandbox continuation v6.5

## Latest local-agent audit

The accepted local-agent base is `ded8db4593c28dd3516ddcaf2ae21cedf6aebfe0`. Revision 8B-B passed its source contract, a 120,000-cycle Revision-8A comparison, a real 512-lane million-step E1 plus 10,000 random-backpressure operations, and a 50,000-operation arbitrary-context test. It has not run any CLN22UL timing phase yet.

## L5.3 blocked Attention stream E0

One Matrix server is shared by QK and PV while SFU work overlaps. FIFO depth was swept.

| Sequence | Selected FIFO | Cycles | Lower bound | Overhead |
|---:|---:|---:|---:|---:|
| 128 | 1/1 | 61,445 | 61,444 | 0.00163% |
| 384 | 1/1 | 479,237 | 479,236 | 0.00021% |
| 1024 | 1/1 | 3,244,165 | 3,244,036 | 0.00398% |

RTL implementation target is 2/2 to absorb service jitter. Score and probability DDR traffic is zero in the model.

## L5.4 fused SiLU x Up DSE

Selected source candidate:

```text
128-entry FP16 direct-SiLU LUT over [-8,8]
ROM                       2,048 bits
fused mean absolute error 0.000333681
fused relative L2         0.000865210
```

The Qwen2 q384 Matrix produces about one fused pair every six cycles on average. One II=1 lane is sufficient analytically; two lanes are preferred for the first mapped comparison.

## Evidence boundary

These are E0 decisions. The sandbox has no Verilator/VCS/DC/Formality/CLN22UL, so RTL E1, mapped equivalence, timing and PPA remain local gates.
