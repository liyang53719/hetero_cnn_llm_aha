# L4 1x1 Conv closeout

Status: PASS. L4 remains `IN_PROGRESS`.

The pinned 1x4x4x3 input to four-channel 1x1 Conv executes the nine-command
production descriptor lowering in retained Gemmini RTL. All 64 INT8 outputs
match an independent NumPy golden; SHA256 is
`2ea021acf608471ed8b4195a49fb534ef3c879a3884e1300d8aa622afe6f8bd6`.

- payload RTL: 514 cycles, 140 semantic DMA bytes, 192 MACs;
- canonical L3 trace: 17 cycles, 256 physical DMA bytes, 256 descriptor bytes,
  seven reads, one write, four conflicts and two read/two write stalls;
- current descriptor-v2 RTL: 85 legal operations and four rejects PASS;
- payload and transport measurements remain separate.

Evidence: `reports/execution/l4_conv1x1_result.json`,
`scripts/run_l4_conv1x1_complete.sh`,
`work/results/l4_conv1x1/conv1x1.log`, and
`work/results/l4_conv1x1_l3_trace/tb.log`.
