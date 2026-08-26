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

The pinned upstream `ScratchpadBank(4096,128,1,false,true,false)` was then
emitted independently through Chisel/CIRCT, without elaborating Rocket or full
Chipyard. Four instances were connected to the gateway and stream network. A
second 100,000-transfer gate passed through the actual upstream write queue,
external-memory ready/valid endpoint, gateway, stream skid, and upstream read
response/fromDMA queue. Generated RTL SHA256 is
`c65a53d98b6029e22371061aa9330031240e9a775813f409707836f139213dad` at upstream
commit `e602d917dcc495c58cabe906535e411707096c9c`; the upstream tree remained clean.

Additional evidence:

- `integration/gemmini/EmitHeteroScratchpadBank.scala`
- `scripts/generate_gemmini_scratchpad_bank.sh`
- `scripts/run_l3_gemmini_pinned_spad_integration.sh`
- `reports/execution/l3_gemmini_pinned_spad_result.json`

This closes pinned Gemmini scratchpad endpoint binding. L3 still requires AHA
and KV production stream endpoints plus the combined command/event/fabric/
stream 100k regression.
