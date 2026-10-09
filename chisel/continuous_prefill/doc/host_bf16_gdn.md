# Host BF16 GDN Dense and Conv prefix

The experimental `bf16Gdn` profile is disabled by default. It uses the production
`HostBlockTop`, one logical Matrix with eight 512-MAC slices, the existing shared
FP32 scalar service, and one iDMA. It implements the GDN QKV Dense projection and
causal depthwise Conv4 plus SiLU. Recurrent SSM, gated normalization, residual,
MLP, full GDN blocks, QoR, and full-model acceptance remain outside this gate.

The minimum numerical test consists of four actual public commands:

1. Dense QKV on cold-prefix token 0, event 0 → 1
2. Cold Conv4/SiLU, publishing token-0 output and history, event 1 → 2
3. Dense QKV on cold-prefix token 1, event 2 → 3
4. Carried Conv4/SiLU consuming the actual published history, event 3 → 4

Both Dense jobs have M=1, K=1024, N=6144. The input is explicitly the raw
normalized-input boundary: real pinned embedding rows for fixed token IDs 19
and 92 pass through the pinned official layer-0 input RMSNorm. InputNorm is not
DUT work. The packer verifies all 14 layer-0 weight pins, all prefix payload
pins, the token fixture, checkpoint revision, configuration, and the pinned
Transformers source. It executes only small lookup, normalization, projection,
and Conv calls; it does not capture a full layer or prefix.

`host_bf16_gdn_descriptor.py` constructs and validates public `Command128` and
`DescriptorRecord` values. Dense uses standard opcode 0x20/engine 2 and 12
records, with `MATRIX_OP → MATRIX_AUX → GDN_POLICY(0x201)`. Conv uses opcode
0x30/engine 3 and 18 records, with `SFU_PROGRAM → GDN_POLICY → GDN_STATE_ROOTS`.
Hin/Hout are real typed tensor roots, channel-major `[6144,4]`. All tensor
prefix/policy indices and all within-command ranges are distinct. The contract
is `config/host_bf16_gdn_descriptor_contract.json`.

`pack_host_bf16_gdn_fixture.py OUTPUT` creates a fresh directory under `work/`.
Use the pinned `work/qk_regen_venv/bin/python` runtime. Projection references
reuse the existing exact integer FMA oracle and independently compiled C
`fmaf` oracle in 48 bounded 256-column heads, covering 12,582,912 FMA steps.
Only terminal values and receipts persist; the maximum head accumulator trace
is 1 MiB and no full-128 reference is generated. Conv expected outputs follow
the frozen separately rounded FP32 multiply/add and degree-7-exp SiLU recipe,
with explicit BF16 RNE boundaries. The actual C++ driver independently checks
both the Dense and Conv recipes before launching hardware.

`verify_host_bf16_gdn_fixture.py FIXTURE` independently regenerates this bounded
proof from the pinned sources, then compares every input, oracle, command,
descriptor, launch binding, and stable manifest field. This takes roughly a
minute. The Python API can instead verify an opaque live same-invocation
`GdnFixtureSession`; caller manifests and digests cannot issue an authority.

The C++ driver `tests/host_bf16_gdn.cpp` accepts `FIXTURE OUTPUT [MODE]`. Its
single memory array is indexed by physical DDR address. Before launch only
commands/descriptors, real normalized inputs, pinned weights, and initial zero
history are loaded. Dense outputs, Conv outputs, histories, allocation gaps,
and guards begin as sentinels. Native/expected arrays exist only in comparison
storage; they are never written into DDR. Conv reads actual prior DMA writes.

The driver checks every earlier output/history after each accepted completion,
all six precise write spans, readonly input preservation, final-write ACK
ordering, completion/result backpressure, event/engine/PC identity, one-iDMA
counts, 64 metadata reads, 147,456 published bytes, and Dense-only useful MACs
of 12,582,912. Conv multiplication work is not counted as Matrix MACs. Conv
publication covers D and Hout separately, including the gap between them.

Modes are `pass`, `last-history-ack-error`, `activation-read-error`,
`weight-read-error`, `output-alias`, and `reset-recovery`. The last-history fault
must preserve previous publications, avoid publishing either failed span, and
require reset. Reset recovery reuses the same DUT and original physical inputs.

There are two separate fixed native gates. Projection and complete end-to-end
Conv/SiLU use max absolute error ≤0.03125 and mean absolute error ≤0.005.
Conv/SiLU on the same canonical Dense inputs additionally require ≤1 numeric
BF16 ULP. Raw bit differences, including +0 versus -0, remain visible; numeric
ULP treats signed zeros as equal. Same-input agreement does not replace the
end-to-end gate. These tests do not claim the native full-block gate passed.
