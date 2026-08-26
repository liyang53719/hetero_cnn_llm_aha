# L4 3x3 Conv identity closeout

Status: PASS. L4 remains `IN_PROGRESS`.

The pinned padded 1x5x5x3 to four-channel 3x3 Conv identity-scale/no-activation
case produces 100 elementwise exact INT8 outputs. Output SHA256 is
`d147231f259c1e9efb8b8e92b9b139c8f09e48da6fc824b0892e56667485ada9`.

- retained Gemmini payload: 847 cycles, 299 semantic bytes, 2,700 MACs;
- canonical L3 trace: 20 cycles, 448 physical bytes, 256 descriptor bytes,
  nine reads, two writes, four conflicts and two read/two write stalls;
- nine CUSTOM_3 commands and current descriptor-v2 RTL regression pass.

The convolution includes its INT32 bias input with identity scale. This does
not close the separately ordered fused requant/ReLU gate.

Evidence: `reports/execution/l4_conv3x3_identity_result.json`,
`scripts/run_l4_conv3x3_identity_complete.sh`, and
`work/results/l4_conv3x3_identity_l3_trace/tb.log`.
