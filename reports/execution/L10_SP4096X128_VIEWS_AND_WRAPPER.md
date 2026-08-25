# L10 SP 4096x128 views and wrapper

The fixed Control/trace SRAM specification now has a bit-write ARM macro at
BASE, 0.8 V, TT25:

- Liberty SHA256: `14965cb35c0a7f8edb57c0fb9a6a8ca9eb3de0862a1ce1560676f6818de99404`.
- Verilog SHA256: `fabe5f2f37fc18c80cd0b83d3c881c99b3956546c47e3e7fb9534dcceffa5779`.
- GDS2 SHA256: `e1c9dfd91af1974ecc73fee4ab20db84d2ded4a81802696629eaac2e58a77848`.

The audit proves 4096 words, 128-bit data, 12-bit physical address and a
128-bit bit-write mask. `ct_sp4096x128_macro_wrapper` presents a 13-bit
ready/valid request interface so addresses 4096–8191 are explicitly rejected.
The real ARM model passes full and partial write/read, stalled response, top
valid address 4095, and invalid read/write tests in 38 cycles. Verilator 5.050
also elaborates the wrapper and vendor model.

Four instances provide the planned 256 KiB Control/trace allocation. This is
functional wrapper readiness, not L10 PASS; DB and LEF remain blocked.

Evidence:

- `scripts/generate_l10_sp4096x128.sh`
- `scripts/audit_l10_sp4096x128_views.py`
- `rtl/memory/ct_sp4096x128_macro_wrapper.sv`
- `tb/tb_ct_sp4096x128_macro_wrapper.sv`
- `scripts/run_l10_sp4096x128_wrapper.sh`
- `work/results/l10_tool_readiness/sp4096x128_views_result.json`
- `work/results/l10_ct_sp_wrapper/tb.log`
