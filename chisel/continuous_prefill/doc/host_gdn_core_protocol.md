# Host GDN core v2, experimental M1 profile

`bf16GdnCore=false` is the default. Enabling it also requires `bf16Gdn=true`
and the existing Qwen3.5 GDN shape. The separate v1 Dense6144/Conv contract is
unchanged when the core flag is false. The v2 profile is M=1, 16 heads,
Dk=Dv=128 only; this is not an M128 prefill implementation.

## Public commands and typed tensors

All commands are existing Command128 records. Dense uses opcode 0x20,
engine 2; the remaining commands use opcode 0x30, engine 3. Every A/B/D
operand, including auxiliary roots, is a normal public typed tensor prefix
(BASE → SHAPE4 → STRIDE3). Storage is contiguous, element-strided, aligned
to 64 bytes, and checked through TypedTensorReader against the launch regions.

A complete launch contains these seven owner operations and terminal Fence:

| Operation | A | B | D | Additional typed roots |
| --- | --- | --- | --- | --- |
| Dense QKV | BF16 [1,1024] | BF16 [1024,6144] | BF16 [1,6144] | none |
| Dense Z | same hidden | BF16 [1024,2048] | BF16 [1,2048] | none |
| Dense AB | same hidden | BF16 [1024,32] | BF16 [1,32] | none |
| Conv | QKV producer D | BF16 [6144,4] | BF16 [1,6144] | BF16 historyIn/out [6144,4] |
| InputPrep | Conv producer D | AB producer D | FP32 [1,6400] | FP32 A_log [1,16]; BF16 dt_bias [1,16] |
| Recurrent | InputPrep producer D | FP32 stateIn [2048,128] | BF16 [1,2048] | FP32 stateOut [2048,128] |
| GatedNorm | Recurrent producer D | Z producer D | BF16 [1,2048] | FP32 weight [1,128] |
| Fence | staged historyOut | staged stateOut | GatedNorm producer D | none |

AB is [A0..A15, B0..B15]. InputPrep's single 25600-byte D allocation contains
Q at +0, K at +8192, V at +16384 and sixteen 64-byte gate records at +24576.
The recurrent state remains FP32. GatedNorm uses the original FP32 weight,
without adding one. Arithmetic behavior is implemented by the real owners;
Host does not inject values or emulate missing producers.

## Policy records

Dense's A tail is MATRIX_OP 0x10 → MATRIX_AUX 0x12 → GDN_POLICY 0x21.
Other commands use SFU_PROGRAM 0x20 → GDN_POLICY 0x21 → optional extra roots.
Fence's policy terminates directly, so its complete descriptor group has
11 records. Fence never issues an owner job.

GDN_POLICY's 72-bit payload:

- [7:0] version = 2
- [15:8] operation = 1 Conv, 2 Dense, 3 InputPrep, 4 Recurrent, 5 GatedNorm, 6 Fence
- [23:16] zero (only layer/stream zero is admitted)
- [24] cold
- [25] recurrentMode; must equal !cold
- [31:26] zero
- [63:32] expected generation
- [71:64] zero

Every command in one transaction carries the same cold/mode/generation.
The first command waits on event zero; every subsequent command must wait on
the immediately preceding command's accepted signal, even if other events
are already signaled.
SFU_PROGRAM retains its public meanings: program_id=0x30, input_count=2,
output_count=1, lane_width_bits=16, vector_lanes=1, program_flags=0.
InputPrep uses input_dtype=5/output_dtype=7; Recurrent uses 7/5; other SFU
commands use 5/5. Operation selection occurs only in GDN_POLICY.

Conv retains GDN_STATE_ROOTS 0x22. InputPrep, Recurrent and GatedNorm use
GDN_AUX_ROOTS 0x23. Both have root0 in payload [23:0], root1 in [47:24],
zero in [71:48], and terminate. Conv roots are historyIn/historyOut;
InputPrep roots are A_log/dt_bias; Recurrent's root0 is stateOut;
GatedNorm's root0 is weight. A single-root record requires root1=0xffffff.
All tensor prefix and policy indices within each command must be distinct.

## Transaction and state lifetime

The three Dense operations execute once each with the exact same hidden
source. Every subsequent arithmetic operand must name its actual producer's
acknowledged output. Readonly reference tensors cannot replace this chain.
Host checks the exact owner tag, zero status, and total acknowledged byte
count before accepting each successful completion. Ordinary completions make
outputs readable only within the active launch; they do not advance the
persistent history, recurrent state or generation.

HistoryOut and stateOut are fresh staging allocations, disjoint from each
other, live outputs, current persistent state and semantic source allocations.
The ten semantic sources (hidden, three Dense weights, Conv weight, A_log,
dt_bias, norm weight, historyIn, stateIn) cannot alias distinct roles across
commands. Repeated hidden references must match exactly. Outputs have SSA
lifetime for the whole launch; last-use buffer reuse is not implemented.
All generated outputs and Fence spans require readable/writable allocations.

The last command must be Fence. Its three typed spans must exactly name the
ACKed staged history, staged recurrent state and final GatedNorm result.
Only the accepted successful Fence completion updates both persistent roots
and increments generation on the same clock edge. A stalled completion,
malformed Fence, missing Fence, intermediate fault, tag mismatch, or wrong
ACK byte count cannot partially commit the persistent context. The old roots
remain protected until the successful Fence.

The first successful Fence also fixes the seven parameter source bindings
(three Dense weights, Conv weight, A_log, dt_bias and norm weight) as part of
the layer checkpoint. Every later warm command must use those exact parameter
spans. All seven committed spans are protected against output writes even
if a later launch changes their region permissions. A different semantic
source, including a new hidden token, also cannot alias any committed parameter
span; this is checked before that source's owner issues. Hidden token inputs may
change across launches. Failed or unfenced
transactions cannot establish or change checkpoint parameter bindings.

A fresh context requires cold=true and generation=0. Later launches require
cold=false, the current generation, and both exact current state roots.
Generation 0xffffffff is rejected. A failed transaction locks the interface
until coordinated reset; reset must also drain/reset owners and transport.
Reset clears the volatile committed context. An explicit checkpoint restore
operation is not implemented in this revision. Cold reset is not a promise
of crash recovery, token replay safety, or state restoration.

## Evidence boundary

HostBlockCommandsGdnCoreSpec is CONTROL_ONLY and uses stand-in owner results.
Its purpose is admission, binding, protocol faults, stalls, persistent-address
protection and atomic publication. It cannot establish numerical correctness,
real DMA ACK behavior, physical resource sharing or complete block closure.
Those claims require the production Host/owner/iDMA chain and its independent
numerical and traffic checks. New source and tests alone are not a passing run.
