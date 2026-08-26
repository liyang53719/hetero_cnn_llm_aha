# L5 q128 SiLU and gate-times-up

Status: PASS; q128 down/final remains `IN_PROGRESS`.

All1,146,880 gate scalars pass through the proven FP32 SiLU and71,680
physical16-lane chunks execute gate-times-up. Every output matches the frozen
operation-order golden; no down output was generated before this gate passed.

Measured totals are10,393,600 cycles:10,321,920 SiLU and71,680 product cycles.
SiLU/product FNV64 values are `c32442fdc4c36c9d` and `846f7a0cfdae4c97`;
SHA256 values are `eb145fa0...` and `661f4f57...`. Maximum SiLU error is
`5.32029292e-5`, below0.002.

Lint/build allocations were about56/520 MB and simulation24 MB under the new
30 GiB cap. No OOM occurred.
