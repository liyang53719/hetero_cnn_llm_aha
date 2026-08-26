# L4 INT8 GEMM closeout

Status: PASS. L4 remains `IN_PROGRESS` for later ordered subgates.

The 17x18x19 OS case is elementwise bit-exact through the production-lowered
retained Gemmini RTL. Payload measurement and canonical-fabric measurement are
kept separate:

- retained Gemmini payload: 955 cycles, 2,195 semantic DMA bytes, 5,814 MACs,
  2.3781086% useful utilization against the physical 16x16 peak;
- canonical L3 trace: 87 cycles, 2,368 physical DMA bytes plus 256 descriptor
  bytes, 36 reads, 5 writes, 5 bank conflicts, 3 read stalls, 2 write stalls
  and 1 descriptor promotion;
- 36 committed CUSTOM_3 payloads match the Python production lowerer;
- current descriptor-v2 RTL regression passes 85 legal ops and four rejects;
- output SHA256 is
  `1d3777b3d32a04238220dc560028765d13e1594e48548a658ac80b3e2c9930d5`.

No analytical cycle or conflict estimate is placed in an RTL-measured field.
The canonical trace replay is a transport/controller measurement; the retained
Gemmini run is the numerical payload measurement.

Evidence:

- `reports/execution/l4_int8_gemm_result.json`
- `scripts/run_l4_int8_gemm_payload.sh`
- `scripts/run_l4_int8_gemm_complete.sh`
- `work/results/l4_int8_gemm/int8_gemm.log`
- `work/results/l4_int8_gemm_l3_trace/tb.log`
- `work/results/l4_int8_gemm_l3_trace/descriptor.log`
