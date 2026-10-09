# Host GDN block v3, experimental M1 profile

`bf16GdnBlock=false` remains the default. Enabling it requires
`bf16GdnCore=true`, `bf16Gdn=true`, and the explicit Qwen3.5 GDN shape. The
v1 Conv and v2 core profiles retain their existing contracts. The v3 profile
admits exactly one complete 17-command, M=1 Qwen3.5-0.8B layer-0 GDN block.
This document describes admission and binding, not a numerical acceptance result.

## Command and descriptor layout

The public format remains Command128. Dense uses opcode 0x20/engine 2;
all other operations use opcode 0x30/engine 3. Every operand uses the existing
BASE → SHAPE4 → STRIDE3 typed tensor chain, with contiguous element strides,
64-byte alignment, normal region checks, and null non-A tails. Each command's
used prefix and policy indices must be distinct.

Dense A tails remain MATRIX_OP 0x10 → MATRIX_AUX 0x12 → GDN_POLICY 0x21,
with the existing BF16 MatrixAux value. SFU tails are SFU_PROGRAM 0x20 →
GDN_POLICY 0x21 → optional auxiliary roots. RMSNorm, Elementwise, and Fence
terminate at GDN_POLICY and have no auxiliary record. Their SFU_PROGRAM has
program_id=0x30, input_count=2, output_count=1, input_dtype=5,
output_dtype=5, lane_width_bits=16, vector_lanes=1, and program_flags=0.
Existing Conv/InputPrep/Recurrent/GatedNorm auxiliary layouts and dtype pairs
are unchanged from the v2 contract.

GDN_POLICY payload fields are:

- [7:0] version = 3
- [15:8] operation: 1 Conv, 2 Dense, 3 InputPrep, 4 Recurrent, 5 GatedNorm,
  6 Fence, 8 RMSNorm, 9 Elementwise; 7 stays reserved
- [23:16] zero, admitting only layer 0 / stream 0
- [24] cold
- [25] recurrentMode, exactly !cold for this M1 profile
- [28:26] explicit operation role
- [31:29] zero
- [63:32] expected generation
- [71:64] zero

Conv, InputPrep, Recurrent, GatedNorm, and Fence require role zero. Every
command carries the same cold/mode/generation. Dense roles are QKV=0, Z=1,
AB=2, O=3, Gate=4, Up=5, Down=6. RMSNorm roles are input=0 and post=1.
Elementwise roles are residual1=0, SiLU-multiply=1, residual2=2.

## Required producer chain

All unmarked tensors below are BF16. Dense weights use [K,N] layout.
The launch has 216 descriptor records when each command owns its prefixes.

| PC | Operation / role | A | B | D | Records |
| --- | --- | --- | --- | --- | --- |
| 0 | RMSNorm / input | raw hidden [1,1024] | original gamma [1,1024] | inputNorm [1,1024] | 11 |
| 1 | Dense / QKV | inputNorm | Wqkv [1024,6144] | QKV [1,6144] | 12 |
| 2 | Dense / Z | inputNorm | Wz [1024,2048] | Z [1,2048] | 12 |
| 3 | Dense / AB | inputNorm | packed Wab [1024,32] | AB [1,32] | 12 |
| 4 | Conv / 0 | QKV | Wconv [6144,4] | Conv [1,6144] | 18 |
| 5 | InputPrep / 0 | Conv | AB | FP32 prep [1,6400] | 18 |
| 6 | Recurrent / 0 | prep | FP32 old state [2048,128] | core [1,2048] | 15 |
| 7 | GatedNorm / 0 | core | Z | gatedNorm [1,2048] | 15 |
| 8 | Dense / O | gatedNorm | Wo [2048,1024] | O [1,1024] | 12 |
| 9 | Elementwise / residual1 | original raw hidden | O | residual1 [1,1024] | 11 |
| 10 | RMSNorm / post | residual1 | original gamma [1,1024] | postNorm [1,1024] | 11 |
| 11 | Dense / Gate | postNorm | Wgate [1024,3584] | Gate [1,3584] | 12 |
| 12 | Dense / Up | postNorm | Wup [1024,3584] | Up [1,3584] | 12 |
| 13 | Elementwise / SiLU-multiply | Gate | Up | SiLU(Gate)×Up [1,3584] | 11 |
| 14 | Dense / Down | SiLU-multiply | Wdown [3584,1024] | Down [1,1024] | 12 |
| 15 | Elementwise / residual2 | residual1 | Down | residual2 [1,1024] | 11 |
| 16 | Fence / 0 | staged history [6144,4] | FP32 staged state [2048,128] | residual2 [1,1024] | 11 |

The Conv extra roots remain old/staged history. InputPrep extra roots remain
FP32 A_log and BF16 dt_bias. Recurrent has the FP32 staged state root;
GatedNorm has the original FP32 gamma [1,128]. RMSNorm owns the gamma+1
arithmetic; the frontend supplies the original BF16 gamma. Elementwise owner
operation 0 performs BF16 residual Add; operation 1 performs BF16 SiLU-multiply.
No pre-normalized hidden or readonly reference output may substitute for an
actual earlier producer. Admission checks prior accepted producers and their
live physical allocations, in addition to the immediate event dependency.

## Publication, physical lifetime, and checkpoint protection

There are 16 owner jobs and 17 command completions. A producer becomes live
only after its exact job tag, successful status, and complete expected write
byte count have been acknowledged and its completion is accepted. The frontend
binds actual BF16 payload byte counts; Conv/Recurrent ACK totals include their
separate staged state writes. Fence emits no owner job.

All intermediate outputs have SSA lifetime through the Fence. Staged states
must be fresh and cannot overlap other live producers, semantic sources,
previous committed roots, or previously committed checkpoint weights. Semantic
sources use distinct roles: raw hidden=0; Wqkv=1; Wz=2; Wab=3; Wconv=4;
A_log=5; dt_bias=6; gatedNorm gamma=7; old history=8; old recurrent state=9;
inputNorm gamma=10; Wo=11; postNorm gamma=12; Wgate=13; Wup=14; Wdown=15.
Distinct roles cannot overlap, including readonly tensors and cold state roots.

Only the accepted terminal Fence after residual2's exact ACK atomically
publishes staged history, staged recurrent state, and generation+1. A stalled
completion, failure, wrong tag/count, or invalid/missing Fence preserves the
old committed context. The first successful Fence binds thirteen checkpoint
parameter spans (roles 1–7 and 10–15). Later launches must use those exact
bindings, and may not overwrite them even when launch region permissions change.
The raw hidden source may change per token.

The first transaction is cold generation 0. A carried transaction requires an
actual prior accepted Fence, its exact two committed roots, and its current
generation. Generation 0xffffffff is rejected. There is no implicit restore
from readonly tensors. Failure locks the interface until coordinated reset;
reset clears volatile context and does not establish checkpoint recovery.

## Evidence boundary

HostBlockCommandsGdnBlockSpec is CONTROL_ONLY, using stand-in owner ACKs to
exercise typed admission, real producer provenance, source/weight protection,
carry context, backpressure, and terminal publication. Its results cannot prove
numerical closure, physical resource sharing, payload DMA, or production ACK
behavior. Those require the real Host/owners/iDMA path and independent reference
and traffic evidence. Unexecuted source or test additions are not passing runs.
