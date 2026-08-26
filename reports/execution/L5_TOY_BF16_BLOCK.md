# L5 toy BF16 block

Status: PASS toy shape; L5 remains `IN_PROGRESS`.

One hidden16 token, four heads of dimension four and MLP width32 execute the
fixed node chain: RMSNorm, Q/K/V, RoPE, online M/L/O attention, OProj,
residual, RMSNorm, gate/up, SiLU, gate multiply, down and final residual.
Every one of 18 saved nodes matches the deterministic Python operation-order
golden. No score matrix is materialized.

The implementation reuses one logical 16x32 BF16 array for every projection
and the closed heterogeneous SFU primitives. Measured cycles are 904 total,
512 Matrix and 364 SFU. Final FNV64 is `e851583bdb646797`; final golden memh
SHA256 is `489ac479686952e04482808b735c506d55e2a39a96a37a776e52ade413c97d68`.

Full lint/build stayed below about 649/1029 MB allocated, within the 10 GiB cap.
This result does not claim hidden256 or target Qwen shape.
