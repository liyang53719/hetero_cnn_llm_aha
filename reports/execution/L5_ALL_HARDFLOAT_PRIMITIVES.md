# L5 joint HardFloat primitive emission

Status: PASS infrastructure readiness; L5 remains `IN_PROGRESS`.

BF16 FMA, FP32 add/mul and FP32 floor converter are now emitted in one Chisel
elaboration, preventing duplicate HardFloat helper modules in block-level
simulation. BF16 child clock/reset ports are explicitly retained while FP32
combinational child interfaces remain clockless. Generated SHA256 is
`94d853130ed0f753de268033dabacaccd1e9b70877326a7d48ba2908b315fc73`.

The same generated file passes the BF16 2x2 accumulation/burst smoke and the
full 10k-vector RMSNorm test. This closes joint-emission infrastructure, not the
toy block itself.
