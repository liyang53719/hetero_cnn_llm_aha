# L5 q128 causal streamed M/L/O and O/L

Status: PASS; q128 OProj/MLP/down phases remain `IN_PROGRESS`.

For every query token0-127 and 12 heads, the RTL streams only causal KV
tokens0..q through dot128 and online softmax. It executes exactly 99,072
updates, 1,536 reciprocals and 12,288 normalization chunks. Only final M/L/O
and attention are saved; no score file or matrix exists.

All outputs match the operation-order model. Measured totals are 3,283,200
cycles: 2,674,944 dot, 589,824 online, 6,144 reciprocal and 12,288
normalization cycles. O/attention FNV64 values are `a61c48b2c07823b1` and
`8087088d974287e9`; attention SHA256 is `b72c3a34...`.

Maximum error against true causal softmax is `6.40920868e-4`, below `0.002`.
Lint/build allocations were about 475/732 MB and simulation 16 MB, with no
OOM.
