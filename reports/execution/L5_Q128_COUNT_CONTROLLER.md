# L5 q128 operation-count controller

Status: PASS for RTL command/count sequencing; q128 numerical payload and
measured latency remain pending.

One synthesizable ready/done controller emits 24 ordered q128 work commands.
It counts 11,698,176 Matrix steps, 114,688 RoPE pairs, 99,072 dot128 and online
updates, 1,536 reciprocals, 12,288 normalization chunks, 1,146,880 SiLU scalars
and 71,680 product chunks. Score-matrix commands are zero.

The command-order FNV64 is `c3b67742c103e99c`. The controller explicitly
holds measured-latency-valid low; the 74-cycle testbench handshake runtime is
not a q128 payload measurement. Lint/build allocations were about 26/226 MB
and simulation 7 MB, with no OOM.
