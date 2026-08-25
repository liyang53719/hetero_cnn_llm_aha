# L3 Matrix direct-stream readiness

The frozen Tensor Stream fields are implemented without adding a route field:
four dedicated channels represent Matrix-to-SFU, SFU-to-Matrix, Matrix-to-KV,
and KV-to-Matrix. Each channel carries 512-bit data, 64 byte enables, 16-bit
tag, 12-bit tensor ID, last, and 4-bit format through a one-entry skid buffer.
Full throughput pop-plus-push is supported and payload remains stable while
valid is stalled.

The deterministic randomized-ready regression transfers 25,000 records per
channel, 100,000 total, in 43,634 cycles. Every field is checked against the
per-channel ordered sequence; mismatch, loss, duplicate, reorder, instability,
and timeout are zero. Verilator 5.050 lint is clean.

Evidence:

- `rtl/common/tensor_stream_skid.sv`
- `rtl/fabric/matrix_direct_streams.sv`
- `tb/tb_matrix_direct_streams.sv`
- `scripts/run_l3_direct_streams.sh`
- `work/results/l3_direct_streams/tb.log`
- `work/results/l3_direct_streams/verilator_lint.log`

This closes the standalone stream contract only. Endpoint connection to the
production Matrix/SFU/KV wrappers and L2 dependency remain before L3 PASS.
