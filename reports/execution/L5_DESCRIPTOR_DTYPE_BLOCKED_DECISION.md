# L5 descriptor public encoding decision — approved

Approved explicitly by the user on 2026-09-01 without changes. The canonical
machine-readable contract is `config/descriptor_public_encoding.json`.

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

The same approval must freeze the previously undefined `0x20 SFU_PROGRAM`
payload. Recommended payload bits are:

- `[15:0] program_id`; dedicated Qwen2 SFU operations use the Command128 opcode
  zero-extended (`0x30` vector, `0x32` RMSNorm, `0x33` softmax, `0x34` RoPE,
  `0x35` activation).
- `[23:16] input_count`, range 1-2; `[31:24] output_count`, currently 1.
- `[35:32] input_dtype`; `[39:36] output_dtype`, using the dtype enum above.
- `[47:40] lane_width_bits`, currently 16 for BF16 tensor boundaries.
- `[55:48] vector_lanes`, zero for a dedicated non-CGRA datapath; nonzero is
  reserved for a registry-defined AHA program.
- `[63:56] program_flags`, currently zero; `[71:64] reserved`, must be zero.

Existing tensor-base conventions remain `memory_space=0` for the flat 56-bit
global address and `layout=0` for contiguous row-major. KV PTE storage does not
consume another dtype value: each 128-bit PTE is described as four INT32 words,
while `kv_table.pte_bytes=16` freezes the record size.
