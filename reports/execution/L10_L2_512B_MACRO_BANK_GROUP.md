# L10 Shared-L2 512-bit macro bank group

`l2_512b_macro_bank_group` realizes one frozen Shared-L2 beat with four
parallel `l2sp6144x128wm` ARM macros. A request is accepted atomically only
when all four lane wrappers are ready; responses are similarly joined before
being exposed. The 512-bit data and 64 byte strobes split into four independent
128-bit/16-strobe lanes.

The real ARM macro model passes full write/read, cross-lane partial writes,
five cycles of response backpressure, and combined invalid-address response.
Result: `L2_512B_MACRO_BANK_GROUP_PASS cycles=36`. Verilator 5.050 elaborates
all four macro instances. Four such groups form the planned 16-bank Shared L2.

Evidence:

- `rtl/memory/l2_512b_macro_bank_group.sv`
- `tb/tb_l2_512b_macro_bank_group.sv`
- `scripts/run_l10_l2_macro_bank_group.sh`
- `work/results/l10_l2_macro_bank_group/tb.log`
- `work/results/l10_l2_macro_bank_group/verilator_lint.log`

This is macro-bank readiness, not L3 or L10 PASS. Arbitration integration,
DB link, and LEF remain required.
