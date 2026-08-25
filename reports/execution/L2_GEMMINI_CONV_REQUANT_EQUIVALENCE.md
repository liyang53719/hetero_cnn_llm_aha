# L2 Gemmini convolution and requant equivalence

One unmodified `GemminiRocketConfig` ran official and project-lowered paths
for a 1x5x5x3 input, padded 3x3 INT8 convolution, four output channels, and
INT32 bias. Two modes were checked: identity output and scale-0.5 plus ReLU.

Result: PASS. All 36 Rocket CUSTOM_3 commits match the Python config and
`ConvWsDescriptor` lowerers; each official/raw pair differs only at its
intentional output destination. Both modes match the independent CPU golden
bit-for-bit. Checksum is `13907229944436499941`; Verilator completed at 199 us
using 285 MB.

Evidence:

- `tests/gemmini_l2_conv_requant_equivalence.c`
- `scripts/audit_gemmini_l2_conv_requant.py`
- `work/results/l2_gemmini_rocc_equiv/conv_requant_result.json`
- `work/results/l2_gemmini_rocc_equiv/verilator_conv_requant.log`
