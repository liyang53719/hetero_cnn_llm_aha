# L2 descriptor-v2 production program vectors

Result: PASS. Schema-v2 record chains are resolved into the pinned Gemmini
programs for the four retained-Rocket L2 cases. Generated funct/rs1/rs2 tuples
match every saved raw Rocket commit: multi-tile OS 36/36, LOOP_WS 11/11,
Conv identity 9/9 and Conv scale-0.5+ReLU 9/9.

The generator commits JSON containing command, descriptor records and decoded
operations plus one 135-bit memh file per case for RTL testbenches. `--check`
detects stale output. The resolver validates Matrix root chains, matrix_aux,
bias, shapes, strides, Conv policy and externally resolved quant scale before
calling the already-audited pinned encoders.

Full Python regression after adding these vectors: 59 PASS. This is the frozen
RTL implementation oracle, not production RTL closure.
