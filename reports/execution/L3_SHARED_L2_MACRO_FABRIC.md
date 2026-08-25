# L3 Shared-L2 real-macro fabric readiness

`shared_l2_macro_fabric` connects the existing four-group round-robin 2R+1W
frontend to four `l2_512b_macro_bank_group` instances, for 16 real ARM
`l2sp6144x128wm` macros and 1536 KiB total capacity. Each read client is limited
to one outstanding transaction; group tags preserve response ownership and
writes consume their internal macro ACK before a group is reused.

The deterministic real-macro regression first initializes the undefined SRAM
power-up contents through the public interface, then executes 100,000 accepted
transactions with held-until-ready requests and randomized response stalls:

- reads: 47,346;
- partial/full writes: 52,654;
- bank-group conflict/stall count: 146,953;
- read stall cycles: 58,367;
- write stall cycles: 88,586;
- total cycles: 168,336;
- mismatch, duplicate, reorder, macro address error, timeout: zero.

The first implementation exposed and fixed an actual handshake bug: a later
unselected group overwrote an earlier group's external ready, allowing an
internal request without an upstream handshake. Ready is now OR-reduced across
groups, and simulation assertions reject any response without a matching
outstanding client.

After diagnostic print removal, the abstract 100,001-transaction regression
and a 3,001-transaction real-macro smoke both pass. Verilator 5.050 elaborates
all 16 vendor macro instances.

Evidence:

- `rtl/fabric/shared_l2_macro_fabric.sv`
- `scripts/run_l3_macro_fabric.sh`
- `work/results/l3_macro_fabric/tb.log`
- `work/results/l3_macro_fabric/tb_abstract.log`
- `work/results/l3_macro_fabric/tb_smoke.log`
- `work/results/l3_macro_fabric/verilator_lint.log`

This remains readiness rather than L3 PASS until L2 passes and direct streams
plus integrated event dependency coverage close.
