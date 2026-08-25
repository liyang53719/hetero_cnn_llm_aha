# L3 descriptor port on real Shared-L2 macro fabric

The approved L2 descriptor request is now mapped onto read client zero of the
production Shared-L2 fabric. `shared_l2_descriptor_port` computes
`descriptor_base + index*16`, selects one of four 128-bit records from the
returned 512-bit beat, permits one outstanding request, propagates macro read
errors, and rejects misaligned/out-of-capacity requests locally. Read client
one and the 512-bit write path remain available to normal engine traffic.

The composition uses the real 4-group × 4-lane ARM CLN22UL 6144×128 SRAM
wrappers. The macro fabric now returns a per-read error bit in addition to its
aggregate error counter.

Results:

- standalone descriptor port: PASS, 1,002 requests including two local errors;
- real-macro contention smoke: PASS, 5,001 transactions;
- real-macro formal run: PASS, 100,001 transactions, 45,415 descriptor/normal
  read responses, 124,022 conflicts, 164,734 cycles;
- zero data mismatch, loss, duplication, timeout or macro error;
- Verilator 5.050 elaboration/lint completed.

Evidence: `work/results/l3_descriptor_fabric/final/`. Commands were bound by
`taskset -c 8-25`; the test used the 10 GiB memory-capped runner. This is L3
readiness evidence. L3 remains dependency-gated by L2.
