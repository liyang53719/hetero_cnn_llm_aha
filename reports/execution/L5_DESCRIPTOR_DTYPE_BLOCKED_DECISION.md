# L5 descriptor dtype decision — approval required

The q1024 graph and 588-command schedule are now traceable to GGML nodes and
GGUF tensors. Packing the descriptor record image is blocked because the
public 4-bit `tensor_base.dtype` enumeration only has production evidence for
`1 = INT8`; BF16 and FP32 codes are not frozen anywhere in the architecture,
schema, RTL, or Git history. GGUF `tensor_type=30` is a storage-format value and
cannot be copied into this 4-bit execution field.

Recommended additive assignment, preserving existing values:

- `0`: invalid/unspecified
- `1`: INT8 (existing)
- `4`: INT32 (existing bias convention)
- `5`: BF16
- `6`: FP16, reserved now
- `7`: FP32

GGUF BF16 weights map to execution dtype 5; GGUF F32 norm/bias tensors map to
dtype 7; runtime token positions use dtype 4. Storage format remains a separate
quantization/GGUF concern. Approval of 5/6/7 permits descriptor-image packing,
legality RTL, and descriptor-backed shared-L2 payload execution. No generated
or upstream RTL is modified by this decision.
