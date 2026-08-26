# L5 complete hidden256 BF16 block

Status: PASS for the complete hidden256 compact block; L5 remains
`IN_PROGRESS` pending target-shape and sequence-length gates.

The fixed workload is hidden256, four heads of dimension 64, two streamed KV
tokens and MLP512. It executes three global RMSNorms; Q, two K, two V, OProj,
gate, up and down GEMVs on the unchanged logical 16x32 BF16/FP32 array; three
RoPE vectors; eight dot64 scores; two-token online softmax; explicit `O/L`;
residuals; SiLU; and gate-times-up. The online update path is exercised and no
complete score matrix is stored.

All 22 frozen nodes are bit-for-bit equal to the operation-order model. The
RTL reports 24,576 physical array steps and 104,902 total cycles: 98,304 Matrix
cycles and 6,598 SFU cycles. The three RMSNorm operations account for 144
reduction, 9 reciprocal-square-root and 48 output-pass cycles. Final FNV64 is
`92aa1cc43e4a6e69`.

The BF16 weight image SHA256 is
`adf8b4e434298b75325f50fb4501adb1371ae06cc234277bcc826cc026ea3cb7`;
the final golden SHA256 is
`0ae337eb1dc5600e3be9128d4a29de70ecea53ec8eac4cdc87716d9843d415e7`.
Strict lint allocated about 812 MB, the j4 build about 1.04 GiB and simulation
24 MB, all under the 10 GiB cap and bound to CPU 8-25.

This evidence is not target-shape, q128, q384 or decode closure.
