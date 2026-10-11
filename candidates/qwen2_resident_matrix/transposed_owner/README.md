# Full-A transposed Dense owner candidate

This is an isolated, default-off source candidate for the actual decoded Dense
owner. It composes real DMA ports, fixed bank memories, the existing Matrix
service, physical result gathering and destination ACKs. It is not a detached
numerical top. Production sources and Host encodings remain unchanged until the
candidate patches are deliberately applied.

The dependency is the frozen transposed-route candidate at commit
`fb909e861ab91dfd7ecc44bc3e86245c3e63b029`. `source_pins.json` records source byte
identities, including the original owner and the model-first dataflow sources.
Apply that candidate's `combined_service.patch`, then `owner_selection.patch`,
and include `DenseOwnerIO.scala`, `TransposedDenseBanks.scala` and
`TransposedDenseOwner.scala` in the production source set. The new kernel
constructor argument `enableTransposedDense` defaults to false. Its Scala
conditional instantiates exactly one Dense owner and one bank allocation.

## Admission and arithmetic contract

- Dense jobs only; M is exactly 16 or 128, 0 < K <= 1536 and K % 16 = 0,
  N > 0 and N % 32 = 0. Native BF16 A additionally requires K % 32 = 0.
- All eight existing activation/weight/output dtype flag combinations are
  represented. The full original pre-DMA alignment, output alias, 56-bit span
  and exact writeBytes checks are retained. A/B overlap is permitted as before.
- FP32 input uses the existing TensorMath.bf16Rne helper. Source NaN/Inf and
  native BF16 NaN/Inf are rejected. Finite FP32 that RNE converts to BF16 Inf is
  now explicitly rejected as Numerical before bank publication; the old owner
  can detect that failure later. This changes failure timing, not the RNE rule
  or the successful finite numerical domain.
- Existing eight endpoints, 4096 BF16-products/FP32-FMA lanes and five FP32
  contexts are unchanged. Each context sees increasing K, with clear only at
  K=0 and terminal emit only at K=K-1. No added FPU, iDMA, Matrix or SRAM exists.
- Bias remains its separate existing owner/Host command. FP32 output preserves
  terminal accumulator bits; BF16 output performs the existing terminal RNE
  with finite threshold abs(bits) < 0x7f7f8000.

## Physical storage and transaction schedule

| Allocation | Payload | Port/schedule |
|---|---:|---|
| A | 16 x 1376 x 256 bits = 688 KiB | One synchronous read + one write per bank |
| B | 16 x 160 x 256 bits = 80 KiB | One synchronous read + one write per bank |
| Operand FIFO | Existing 4 x MatrixStreamStep | Credit includes the pending SRAM response |
| A ingress | 256-bit RMW payload + 256-bit native upper half | 512 bits total; no 4096-bit response hold |
| Final value | Existing 16 x 256 x FP32 = 16 KiB | One complete physical result |
| Matrix storage | Existing five contexts, metadata8, result2 | No new payload buffer |

A[k,m] maps to bank=(k&15) xor (m/16), word=(k/16)*8+m/16,
lane=m%16. The admitted full-A range uses words0..767; the physical allocation
still has depth1376 and its clear/write address port is11 bits. Row indices
are seven bits (0..127); comparisons use widened +& to represent terminal128.
All used A words are physically cleared before loading, including M16 padding.
Each accepted source beat initiates a bank read and captures its converted
256-bit payload; the next edge unconditionally merges and writes the sixteen
bank responses. Native BF16 serializes a second pass using the upper hold.
Neither pass can stall its return or silently infer another memory port.
A becomes committed only after the final validated DMA terminal and all RMW
writes complete. Its local generation counter does not establish reset-domain
freshness.

B linear=half*1280+(k%128)*10+(2*context+nHalf), bank=linear%16,
word=linear/16. The highest physical word is159. A half is published only after
all its expected descriptors finish successfully. Reads check the committed
half's K and N-window identities. The consumed half may be reloaded after its
last synchronous read has reserved a FIFO slot. Five contexts cover N160;
the final window uses only the required N32 contexts and K128 depth tail.

This first source gate intentionally uses one-beat real burst-read descriptors.
It proves a conservative port/control composition, not a coalesced or optimized
throughput schedule. B prefetch and matrix issue can overlap in opposite halves.

Accepted step payloads are a[0..15]=weightN0..15,
b[0..127]=activationM0..127, b[128..143]=weightN16..31; all remaining lanes zero.
The accepted group fixes transposed mode, opcode0x20 and mask0xff. Physical
result mapping is Y[m,n]=physical[n%16][32*(4*(n/16)+m/32)+m%32]. Stores gather
16 physical rows for FP32 or32 logical cells for BF16. A result must follow its
accepted terminal step and arrive in context order. Results and stores drain
before Matrixdone; waiting for done first would deadlock five contexts against
the two Matrix result buffers plus the owner's one final buffer.

## Completion, faults and reset assumptions

Success requires every accepted Matrix step/result, Matrixdone, all destination
ACKs, exact acknowledged output bytes and empty operand/read/write obligations.
The owner issues no new work after a fault, drains already accepted write data
and physical terminals, aborts Matrix, returns one error and locks. The kernel
also blocks other owners after shared poison when this profile is enabled.

The existing adapters provide one controlled outstanding transaction per port.
An accepted Matrixdone or write response is the sole physical terminal even if
its tag is malformed. Reads drain their expected descriptor beat count (one in
this candidate); wrong LAST/tag fails the transaction and cannot publish data.
These malformed terminals retire the physical obligation, preventing a wait
for a second terminal the adapter will never send. The owner cannot accept
another job until a coordinated reset. Unsolicited/cross-job stale responses
are outside this sole-outstanding adapter contract and must be prevented at
the shared DMA/Matrix reset boundary. Local counters are not evidence of that
fence. A missing physical terminal has no bounded-liveness guarantee.

## Checks and limits

Run the independent clocked port/FSM model tests with:

    python -m unittest discover -s candidates/qwen2_resident_matrix/transposed_owner -p 'test_*.py' -v

The model accepts externally supplied physical Matrix results; it executes no
FPU and is not RTL simulation. It checks bit routing against the frozen route,
bank port reservations, backpressure, failures and accepted-edge races.

`check_frontend.py --out NEW_DIRECTORY --cache EXISTING_VERIFIED_JARS` uses the
87 SHA-pinned cached dependencies, one Java CPU, max heap1024 MiB and180-second
limits per compile/emission command. `--validate-only` checks source/patch/ABI
and cache identity without compiling. It compiles real owner/bank/service
sources, uses exact existing retained BlackBox declarations, and emits only
CHIRRTL. It compares the old owner with the shared-IO disabled owner, then
counts physical memories/ports and fixed queue/result allocations for both
single and burst writes. The full QwenOwnerKernel is not elaborated here; its
actual patched canStart expression is extracted for a separate frontend probe.
Optional `--hardfloat PINNED_CHECKOUT` additionally typechecks the entire frozen
production main/P0/gemmini source set with HardFloat commit
`c1105e6ac6a0dd90fc80893efc4830ab609005d3`, after applying the candidate patches.
It never runs a production Emit entry point or elaborates the whole kernel.
No firtool, SystemVerilog, Verilator, endpoint arithmetic or full block is run.

Down-projection prefix restoration, FFN fusion and Host full-block composition
remain open. The old ResidentCSeedReader's partition/address widths are not
compatible with these banks and it is not connected. Native-M128 and FP32-final
FAIL evidence, numerical policy pending, timing, physical area, throughput,
hardware reset behavior and complete Host acceptance are unchanged.

## Bounded real-input numerical closure

`check_numeric_smoke.py --out NEW_DIRECTORY` is a separate, at-most60-second
host-model check of one derived M128/K1536/N160 Dense group, using SHA-pinned
saved n0 and the first160 Q-projection weight rows. It does not execute the
complete projection or block. It compiles the tiny `numeric_smoke.cpp` shared
library with strict FP flags; each actual accepted bank-model payload advances
the five physical host accumulator contexts with increasing-K std::fma. Actual
terminal results return to the same model instance and traverse result gather,
write data and ACK before comparison. Independent raw-input dot products are
computed only after that owner finishes and never supply its result port.

The completed run produced7680 accepted steps,31,457,280 FMA updates,
1280 output beats and640 successful ACKs covering81,920 bytes. All20,480
pre-bias output cells matched the independent direct dot reference bit-for-bit.
Adding the separate original recipe bias after ACK also matched the corresponding
saved qr cells bit-for-bit. These are v0 host-model checks only; all hardware,
native-M128 and FP32-final acceptance limitations above still apply. Protocol
model ticks do not predict physical Matrix latency or hardware cycles.
