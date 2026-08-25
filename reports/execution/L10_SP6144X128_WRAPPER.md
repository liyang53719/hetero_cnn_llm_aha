# L10 SP 6144x128 production wrapper

`l2_sp6144x128_macro_wrapper` binds the generated ARM
`l2sp6144x128wm` macro to one ready/valid request and response channel.
It fixes the compiler-recommended 0.8 V assist settings, converts sixteen byte
strobes to the macro's active-low 128-bit write mask, returns an ACK for writes,
holds read data under response backpressure, and rejects addresses 6144–8191
without accessing the macro.

The directed Icarus test uses the real generated ARM model and passes:

- full 128-bit write/read;
- partial write with independent byte golden merge;
- response stability for four stalled cycles;
- invalid read and write rejection.

Result: `L2_SP6144X128_MACRO_WRAPPER_PASS cycles=39`.
Verilator 5.050 also elaborates the wrapper and generated macro; reported
latches are internal to the vendor behavioral model.

Evidence:

- `rtl/memory/l2_sp6144x128_macro_wrapper.sv`
- `tb/tb_l2_sp6144x128_macro_wrapper.sv`
- `scripts/run_l10_sp6144x128_wrapper.sh`
- `work/results/l10_sp_wrapper/tb.log`
- `work/results/l10_sp_wrapper/verilator_lint.log`

This closes functional wrapper readiness only. DB link and LEF remain blocked
by external tools, and L10 remains PENDING.
