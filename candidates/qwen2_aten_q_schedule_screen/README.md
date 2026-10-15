# Conditional Q-projection reduction schedule screen

Status: BLOCKED_UNIMPLEMENTED_MAPPING. This is a small integer-only architectural
screen, not Chisel, RTL simulation, a numerical candidate, a cycle predictor, or
a hardware utilization measurement. CPU reduction order does not establish that
the existing hardware must change: first compare the unchanged DUT against the
new official reference using its existing error gate. This screen only prices a
possible exact 8x8 partial-sum mapping if that independently becomes necessary.

## Resource evidence

`screen.py:SOURCES` pins five read-only resource/control sources. MatrixPipeline.scala
instantiates eight retained 16x32 endpoints: 4096 BF16-product/FP32-FMA lanes,
five contexts, and one shared A16 vector broadcast to all slices plus B256.
Each leaf accepts context 0..4, not an arbitrary accumulator address. A step
carries 32 B A and 512 B B. Five accumulator contexts contain 20480 FP32 words,
81920 B. MatrixPipeline includes two 16 KiB result buffers; existing retained
result registers, metadata and finalValue also remain distinct storage, not
free new accumulators. The source recurrence is five cycles, as documented in
the pinned transposed-dense resource inventory.

The existing Vector loan has sixteen FP32 Add lanes. Its model explicitly says
it is not a connected bank/Dense RTL implementation, and its injected latency
is not a hardware measurement. The tile sum controller uses existing tile ports
plus one sixteen-word lhs hold. Neither demonstrates this new reduction tree.

## Arithmetic contract supplied by the numerical candidate owner

For each output, maintain S[r][l], r,l in 0..7, initialized to +0. For t=0..23,
update with k=64*t+8*r+l. Register reduction uses offsets 4,2,1, followed by lane
reduction offsets 4,2,1. That is 56+7 FP32 adds, followed by an explicit +0 tail
add, then one bias add, then BF16 RNE once. Counts per output: 1536 FMA and 65
FP32 adds. This file does not validate that arithmetic or compare any tensors.
Partial FP32 sums cannot simply be fed through BF16 input multiplication to
pretend that the tree additions are free equivalent FMA operations.

## Two conditional maps, neither connected

1. Conservative existing-width sparse outer product: context maps 16 M rows x
   4 N outputs x 64 partials into physical row=m and col=64*n+p. At each k, only
   p=k%64 updates. A16 remains the existing broadcast; B256 supplies only the
   four selected output weights. Five contexts retain 320 outputs, using exactly
   the existing accumulator capacity. There are only 64 useful products per
   4096-slot issue: geometric issue fill is 1/64, or 1.5625%, before every other
   cost. A k%64 value cannot be sent as context: the interface has only five.
   Per-column accumulator write enable/hold and sparse B routing are REQUIRED
   but NOT implemented. Updating inactive lanes using x*0+acc is not accepted as
   an equivalent hold, because signed-zero/error behavior needs proof.

2. Wide-K hypothesis: 8 M x 8 N outputs, each with 64 independent K lanes, uses
   4096 FMA slots and 4096 partial words/context. It geometrically fills the
   array but needs 512 distinct BF16 A and 512 BF16 B values per issue, 1024 B
   each. Existing outer-product broadcasts cannot express these pairings. Even
   serial delivery on the old A16 port takes at least 32 service units/issue;
   B256 needs at least two. Staging/gather/cell routing is not implemented or
   credited as zero-area logic. There is no new compute lane or SRAM in this
   screen, and no proof that available existing buffers can be wired as needed.

Both require partial-output capture into existing result/resident storage,
explicit in-place tree routing through the SAME sixteen Vector lanes, mutual
exclusion with other Vector owners, exact level dependencies, bias/rounding,
output ordering, completion/ACK and error/backpressure handling. They are blocked
until these interfaces and controls exist. No whole-block throughput is inferred.

## Complete conditional denominator

Boundary: complete M128,K1536,N1536 projection from supplied widened FP32
activation and BF16 weight reads through widened FP32 final Q store/ACK. It does
not include preceding RMS normalization or following RoPE. Useful work is
301989888 FMA, never padded/zero products.

The integer ledger charges all ten disjoint serialized phases:
- useful/padded issue schedule including five-cycle recurrence and tail contexts
- pipeline fill/drain at every group
- operand stream delivery (one or at least 32 units/issue)
- external activation, weight, bias and final output transfers
- every 64-partial snapshot write
- two reads plus one write for every tree, tail-zero and bias add
- all 16-lane Vector service requests
- final result reads
- BF16 rounding/widening service
- command/completion/ACK control

One external activation/weight read and final output write are an explicitly
optimistic reuse assumption, not measured traffic. A activation storage can hold
the BF16 activation set; a K1536xN4/8 weight window fits existing B capacity. Real
bank address conflicts, refill/routing/descriptor costs can increase the ledger.
Existing memory inventories are 16 banks x32B words, A704512 B and B81920 B;
capacity does not prove port accessibility. Vector tree words are reused in-place
in existing storage; no extra hidden partial array is admitted.

`Assumptions` exposes positive service costs. Defaults use optimistic one-unit
transfers, one-unit 16-lane Vector requests and conversion, plus four control units
per tile. These are NOT implemented cycle latencies. The serial ratio is merely
conditional on those assumptions. A separate perfect-overlap resource ceiling
uses max(phase costs), not their sum; overlap itself is unproved. Neither number
is measured utilization or a promised schedule. All hardware cycle/prediction/
measurement fields stay null, and both routes remain BLOCKED.

Run cold checks with `python -B -m unittest candidates.qwen2_aten_q_schedule_screen.test_screen`.
Run the integer-only source-verified ledger with `python -B -m candidates.qwen2_aten_q_schedule_screen.screen`.
No native arithmetic, checkpoint, numerical output or running closure is touched.
