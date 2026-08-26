# L3 AHA and KV production stream endpoints

Status: readiness subgate PASS; L3 remains `IN_PROGRESS`.

`aha_tensor_stream_endpoint` connects Tensor Stream channels 0/1 to the
official Garnet `proc_packet` boundary. Input addresses are supplied by the
registry/configuration layer; the wrapper does not invent an AHA bank mapping.
Each 512-bit beat is emitted as eight ordered 64-bit writes through the existing
`aha_garnet_proc_packet_writer`. Native EOS pulses only after `packet_done` for
the final beat. The read side issues eight continuous official proc-packet
reads and buffers a complete 512-bit output before presenting it to the stream.

`kv_tensor_stream_endpoint` connects channels 2/3 to an external 512-bit KV
staging memory request interface. It implements no flop-backed staging array;
the 512 KiB store remains an external SRAM wrapper responsibility. Writes
preserve 64 byte enables and validate input tag/tensor/format. Reads allow one
outstanding request and hold data plus sideband stable under backpressure.

The deterministic Verilator 5.050 gate passed 100,000 mixed transfers:

- 50,000 AHA input/process/output transactions;
- exactly 400,000 ordered 64-bit AHA writes and 400,000 reads;
- 25,000 KV staging writes and 25,000 byte-exact reads;
- all four direct-stream channels made progress under backpressure;
- completion followed final source-side stream acceptance;
- zero mismatch, protocol error or timeout;
- strict `-Wall` lint is clean.

Evidence:

- `scripts/run_l3_aha_kv_endpoints.sh`
- `work/results/l3_aha_kv_endpoints/verilator_lint.log`
- `work/results/l3_aha_kv_endpoints/verilator_build.log`
- `work/results/l3_aha_kv_endpoints/tb_100k.log`
- `reports/execution/l3_aha_kv_endpoints_result.json`

This does not close L3. The endpoints still need composition with the production
Shared-L2 arbiter, command/completion FIFOs, real event SRAM, timeout policy and
pinned Gemmini gateway in one integrated 100k regression.
