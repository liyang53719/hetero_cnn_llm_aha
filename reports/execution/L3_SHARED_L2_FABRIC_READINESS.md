# L3 shared-L2 fabric readiness

This work prepares, but does not close, canonical L3 while L2 remains open.
The prior contract memory modeled one flat 512-bit word per address. It has
been replaced by 16 logical 128-bit banks. Each 512-bit beat maps to four
consecutive banks using `group=beat_addr[1:0]` and `row=beat_addr>>2`.

Two read clients and one write client arbitrate independently in each of four
bank groups with round-robin priority. Read responses hold under backpressure;
write byte enables operate across all 64 bytes. Cycle, accepted read/write,
bank-conflict, read-stall, and write-stall counters are implemented.

Icarus randomized result: PASS at 100,001 accepted transactions, including
52,898 reads, 47,103 partial-byte writes, 15,414 bank conflicts, 8,086 read
stall cycles, and 7,328 write stall cycles over 77,897 cycles. Requests remain
stable until ready and responses are checked against an independent model.
A directed hierarchical check proves beat address 6 maps to row 1 of banks
8–11. Verilator 5.050 lint is clean.

Evidence:

- `rtl/fabric/shared_l2_fabric.sv`
- `tb/tb_shared_l2_fabric.sv`
- `work/results/l3_fabric_readiness/tb_shared_l2_fabric.log`
- `work/results/l3_fabric_readiness/verilator_lint_clean.log`

Remaining L3 scope includes direct engine streams, event dependency tests,
timeout assertions, and integrated 100k command/event traffic. L3 cannot be
marked PASS before L2.
