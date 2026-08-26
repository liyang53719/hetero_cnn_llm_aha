# L5 BF16/FP32 FMA lane

Status: PASS lane primitive; L5 remains `IN_PROGRESS`.

One lane is emitted from pinned HardFloat commit
`0ecaef097ce2accbd16a61613699450ed5533f29`. BF16 operands are exactly expanded
to FP32 and evaluated by `MulAddRecFN(8,24)` with RNE and tininess after
rounding. Generated RTL SHA256 is
`69a8164bd1d6f29ce8770060b2c6a194b6b8a4a02d9322f91841ae76ef2ce6aa`.

10,000 vectors match libm `fmaf` bit-for-bit. Inf times zero plus one produces a
NaN and HardFloat invalid flag `0x10`. Output FNV64 is
`ab56c8ee63a63aeb`; vector SHA256 is
`4210d4cfd2d59b6be4611691a567d9d83370648708d7d986ceb063a41844376e`.

Generated-source filename/timescale/unused-wire warnings are explicitly scoped
waivers; project testbench lint is otherwise strict. This lane does not yet
prove the required 16x32/512-MAC array.
