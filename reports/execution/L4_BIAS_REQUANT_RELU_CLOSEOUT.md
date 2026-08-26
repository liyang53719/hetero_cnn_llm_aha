# L4 bias, requant and ReLU closeout

Status: PASS. L4 remains `IN_PROGRESS`.

The padded 3x3 Conv fused mode uses INT32 bias, FP32 0.5 scale with RNE and
ReLU. All 100 outputs match an independent NumPy float32/RNE golden. Output
SHA256 is `a1ca1a974218073bc49bcdf11173df9452bc427bb46040b70f0131da71b1126d`.

- retained Gemmini payload: 837 cycles, 299 semantic bytes, 2,700 MACs;
- canonical L3 trace: 20 cycles, 448 physical bytes, four conflicts and two
  read/two write stalls;
- nine CUSTOM_3 operations match `conv_relu_requant` descriptor vectors.

Evidence: `reports/execution/l4_conv3x3_relu_requant_result.json` and
`scripts/run_l4_conv3x3_relu_requant_complete.sh`.
