# L2 Matrix auxiliary descriptor BLOCKED_DECISION

The approved Shared-L2 transport is complete, but the frozen schema cannot
unambiguously lower all required official Gemmini paths. A command has only
`src0/src1/dst`, while biased GEMM and convolution require A/input, B/weights,
C/output and D/bias. The existing `subtype` and common `flags` fields have no
frozen role semantics. Official LOOP_WS/Conv operands also require `full_c`,
`low_d`, repeating-bias, activation, transform and subarray policy that is not
present in `matrix_op` or `conv2d`.

Recommended extension: add record type `0x12 matrix_aux`, chained from the
Matrix operation descriptor, with this 72-bit payload:

- `[79:56] bias_index` (24 bits, `0xFFFFFF` means no bias; otherwise selects a
  normal tensor_base/shape/stride chain);
- `[81:80] activation`;
- `[82] full_c`, `[83] low_d`, `[84] repeating_bias`;
- `[85] no_pool`, `[86] downsample`, `[87] input_dilated`, `[88] wrot180`;
- `[89] trans_output_1203`, `[90] trans_weight_1203`,
  `[91] trans_weight_0132`, `[92] trans_input_3120`, `[93] depthwise`;
- `[95:94] a_spad_id`, `[97:96] b_spad_id`;
- `[105:98] max_pixels_per_row`;
- `[127:106] reserved`, required zero.

Quantization remains the existing `0x40 quantization` record in the output
chain; no second auxiliary pointer is introduced. Conv pooling remains
disabled in L2 (`no_pool=1`); pooling is closed in L4 through the planned SFU.

This preserves the 128-bit command, uses typed descriptors rather than a
pre-lowered FIFO, and supplies every policy bit consumed by the already-pinned
official LOOP_WS/Conv encoders. Approval is required before changing
`spec/descriptor_schema.yaml` or production RTL.
