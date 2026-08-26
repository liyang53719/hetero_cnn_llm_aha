# L5 q384 split-half RoPE and K/V GQA

Status: PASS; q384 causal attention and downstream phases remain pending.

The runtime-configured RoPE/GQA binary executes q384 then q128 without
recompilation. q384 performs344,064 split-half pairs and73,728 K/V multicast
outputs in1,474,560 cycles. q128 compatibility reproduces historical FNVs.

Q-RoPE/K-GQA/V-GQA SHA256 values are `5081f415...`,`1864dc6d...`,`d073bb85...`.
The shared binary SHA256 is `deaaede1...`. Build allocation was625 MB and q384
simulation17 MB, with no OOM.
