# L5 independent BF16 16x32 array

Status: PASS. L5 remains `IN_PROGRESS`.

`bf16_outer_product_array` is independent of the INT8 PE path. It instantiates
512 pinned HardFloat BF16xBF16+FP32 FMA lanes behind a two-stage elastic
ready/valid interface. The logical geometry is 16 rows by 32 columns and
therefore performs 512 BF16 MACs per accepted outer-product step.

The parameterized 2x2 smoke passes before full elaboration. The full 16x32
array passes four dependent K-accumulation steps for all 512 FP32 lanes and an
eight-tile independent burst accepted in eight consecutive cycles. Final
accumulator FNV64 is `7da144b97d054b25`; exception flags and mismatches are
zero. Strict project lint passes with only generated HardFloat warning waivers.

Full Verilator conversion allocated about 492 MB; build and simulation stayed
inside the 10 GiB cap. This proves logical throughput and numerics, not yet
1 GHz synthesis timing or the L5 SFU/block workload.
