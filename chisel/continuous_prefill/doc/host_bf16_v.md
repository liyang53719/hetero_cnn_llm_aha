# Experimental Host V-only BF16 storage

The opt-in `bf16V=false` constructor capability defaults off. `EmitHostBf16V`
explicitly emits the H1024 / context-Q2048 / packed-Q4096 / KV512 / FFN3584
profile. The ordinary Host emitter and existing positional shape constructors
retain their defaults. This profile supports only V projection. Q/K, norms,
RoPE, attention, FFN and the complete Qwen3.5 block fail closed.

The route is the existing production `HostBlockTop -> HostBlockCommands ->
QwenOwnerKernel -> StreamingDenseOwner -> MatrixPipelineService`, with eight
retained 512-MAC slices and the existing single pinned iDMA adapter/backend.
There is no QKV candidate instance, extra Matrix, second DMA, Host-injected
Matrix results, or matrix arithmetic replacement.

## Descriptor and ownership contract

`config/host_bf16_v_descriptor_contract.json` defines version 2 of the existing
0x1a/0x1b extension wire records. `scripts/host_bf16_v_descriptor.py` is its
separate serializer/preflight checker. The separate proposed SharedL2 candidate version 1 is outside this Host release.

- Ordinary opcode 0x20, engine 2, zero flags, ordinary wait/signal events
- Three typed BF16 rank-2 tensors with `(M,N,1,1)` shapes and element strides
- All 21 record indices distinct, exact ordered chains and termination
- MatrixAux BF16-output defaults, separate from the old full_c FP32 policy
- Version 2, role V, tensor=1, tile16=1, norm_policy=0, reserved=0
- All nine local/extra-output addresses are zero sentinels

The mode's tile16 bit states arithmetic granularity. It does not impose a
16-token batch or expose private SRAM addresses. The owner chooses bounded
staging, multiple retained contexts, and later token batches internally.

Full tensor allocations and region permissions are validated before the active
window. The job binds `m=count,n=512,k=1024`, A offset `base*2048`, D offset
`base*1024`, and `writeBytes=count*1024`. A/B/D storage flags are all explicit.
Only the active D span becomes readable after a correct owner completion with
an exact acknowledged byte count and acceptance of its Host completion event.
Untouched prefix/suffix bytes are never published.

## Native storage behavior

A native 64-byte beat contains 32 BF16 values. Its upper 256 bits are held for
one cycle, while the same single write port used for the lower half writes the
upper half. Response backpressure protects that held half; no SRAM port or
bank is duplicated. Old FP32 input conversion remains unchanged.

Accumulation remains increasing-K BF16 x BF16 + FP32. Output conversion uses
`TensorMath.bf16Rne`, packing 32 BF16 elements per write beat for both scalar
and burst writeback. Before any store from a final result tile, all active
values must be finite after BF16 RNE; `abs(bits)>=0x7f7f8000` is rejected. Inactive
rows/columns do not affect this check. Completion follows write acknowledgments.

## Verification and scope

The Scala Host suite controls only descriptor memory and owner completion.
The Dense storage probe controls Matrix returns and checks feeder/protocol and
rounding behavior. Neither suite is an arithmetic or real-iDMA acceptance test.

`pack_host_bf16_v_fixture.py` loads the code-pinned verified official prefix
capture, normalized layer3 producer07, full checkpoint V weights, and native V
producer26. It retains full 128-row allocations and both native full-block
failure flags. Payloads and generated build artifacts stay in ignored `work/`.

`run_host_bf16_v_gate.sh OUT FIXTURE [burstWrites]` is the actual Host/retained
Matrix/pinned-iDMA numerical gate. It accepts a verified offline tool catalog or ordinary SBT with an isolated
task-local Maven cache, and requires a verified iDMA source export. The pinned
public source export can be rebuilt with `prepare_pinned_idma_sources.py`. The C++ harness supplies only AXI memory and computes an independent
sequential-K std::fma oracle before launch. It checks every BF16 result, guards,
AXI backpressure, delayed final acknowledgment, and injected final-write/read
errors. Native producer comparisons are reported separately from canonical
bit identity. Run a representative window before full M128.

Passing V tests does not close the existing native full-block failures, Q/K,
three-model block acceptance, performance, synthesis QoR, timing, or MAC90%.

`verify_host_bf16_v_fixture.py` replays the Host-local source pin and compares
canonical fixture bytes, so caller-edited self-hashed manifests are rejected.
`run_host_bf16_v_replays.py` extends a passed, immutable production DUT with
nonzero windows and optional full128 baseline/AVX2 cold/carried cases. The new
runner identity is separate from the original build receipt. Neither helper
imports or requires the proposed SharedL2 policy-1 candidate implementation.

## Source-pin transition and evidence boundaries

The first local numerical run used the already-verified official capture at
manifest SHA256 `21eb0f6f3f59b3b1a33650a07692084eabe69a0d04cec60036a434357b2c1b02`.
The Host packer now owns that source pin directly. It does not import the
proposed SharedL2 command candidate to obtain it. Repacking the representative
case, both nonzero windows, and all four full128 cases produced byte-identical
activation, transposed weight, native comparison, command, descriptor, and
launch files. Only source-receipt hashes changed. Original numerical receipts
are preserved; the equivalence receipt binds the later packer separately.

Local verified coverage includes:

- Production Host decoder: default-off, V-only, strict chains, bounds, aliases,
  event/job backpressure, exact acknowledged-window publication
- Existing FP32/native-weight metadata paths, including real16 two-layer graphs
- Scalar and burst Dense storage/controller checks, with injected Matrix
  results explicitly distinguished from arithmetic verification
- Actual retained Matrix plus pinned iDMA: authentic token1 V and failure of its
  final write acknowledgment; base1/count17 and base47/count81 windows; full128
  cold/carried for baseline and AVX2
- All 312,320 values across the six window/full128 replays matched the ordered-K
  reference exactly. Each native V operator comparison passed its fixed gate
- Reachable hierarchy audit: one logical Matrix service, eight original
  512-MAC slices, one pinned iDMA backend, and no standalone fallback MAC

These are V-component results. The original native all-producer/full-block
failures remain in every source receipt. A separate fresh-source entry point
can rebuild the official prefix in one invocation and authenticate that new
capture; its receipt must not be substituted for the earlier capture's receipt.

The old Qwen2 real16 actual two-layer numerical/lifecycle regression is a
separate gate from metadata tests and V arithmetic tests. Do not infer it from
the results above. Build controls may cap compiler memory and reclaim completed
PCH files, but cannot edit HDL or substitute arithmetic/DDR services.
