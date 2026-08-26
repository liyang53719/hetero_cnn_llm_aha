# L3 Gemmini scratchpad Tensor Stream gateway

Status: readiness subgate PASS; L3 remains `IN_PROGRESS`.

The production gateway adapts four pinned-Gemmini `ExtMemIO` scratchpad banks
(128 bits each) to one 512-bit Tensor Stream beat. It preserves byte enables,
tag, tensor ID, format, route and final-beat state under backpressure. The
reverse direction accepts only full 512-bit beats because Gemmini read
responses have no byte-enable field; a partial beat is rejected as a protocol
error.

The deterministic gate completed 100,000 configured transfers:

- 50,000 Matrix-to-SFU/KV stream beats;
- 50,000 SFU/KV-to-Matrix stream beats;
- 200,000 independently backpressured 128-bit bank responses;
- both SFU and KV routes made progress;
- zero mismatch, protocol error or timeout;
- Verilator 5.050 `-Wall` lint is clean.

Evidence:

- `scripts/run_l3_gemmini_spad_gateway.sh`
- `work/results/l3_spad_gateway/tb_100k.log`
- `work/results/l3_spad_gateway/verilator_lint.log`
- `reports/execution/l3_gemmini_spad_gateway_result.json`

This proves the project-owned endpoint adapter, not final Gemmini integration.
L3 still requires binding the adapter to an emitted Gemmini external-scratchpad
port, AHA/KV production endpoints, and the combined command/event/fabric/stream
100k regression.
