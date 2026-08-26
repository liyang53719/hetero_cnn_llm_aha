# L5 q384 prefill operation contract

Status: PASS for shape/count lock only; q384 numerical and measured cycles are
pending.

Batch1/sequence384 uses24 physical16-row batches. Matrix steps are Q/O
1,769,472 each; K/V294,912 each; gate/up/down10,321,920 each; total35,094,528.
The causal prefix sum is73,920 per head and887,040 head-token updates. RoPE is
344,064 pairs; reciprocals4,608; O/L chunks36,864; SiLU3,440,640 scalars;
product215,040 chunks. No score matrix is permitted and measured cycles remain
null.
