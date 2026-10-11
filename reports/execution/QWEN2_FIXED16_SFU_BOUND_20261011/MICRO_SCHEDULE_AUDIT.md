# Same-recipe temporal SFU scheduling: read-only design audit

No hardware or cycle-model implementation is provided here. This is a proposed resource contract for a later software model. It changes control scheduling, not the RNE recipe or approximation. Current measured hardware cycles remain unknown.

## Arithmetic reservation ledger

BlockFloat.scala:90–98 implements nonsaturated ExpNegative with:

- scale: one Mul
- floor: one RecFNToIN conversion; k is retained as UInt8
- fraction: one Add, using the existing INToRecFN conversion of k
- seven Horner stages: seven Mul followed by seven Add, with separate FP32 rounding
- exponent restoration: one Mul

Thus exp needs 17 selected ALU operations: 9 Mul and 8 Add. The floor state accounts for the eighteenth processing-state visit, but is not an eighteenth ALU operation. The SiLU wrapper adds one Add and three Mul, producing 21 selected ALU operations per nonsaturated element (12 Mul, 9 Add), plus one Div. Saturated exp can bypass its discarded internal scale result in a proposed controller, leaving the four external Add/Mul operations and one Div; this shortcut has not been implemented or numerically validated.

The ALU and DivSqrtRecFN_small are physically distinct instances (BlockFloat.scala:48–54). Their current single state machine serializes them. A new scheduler can in principle run context B's exp while context A waits for its divider, with no new ALU/divider. This requires a real context table, operand selection, divider return ownership, write arbitration and poison/drain behavior.

Treat the ALU as one selected operation per lane per cycle, matching its single x/y/op/out interface. HeteroFP32Alu contains separate AddRecFN and MulRecFN circuits, but their common operands and selected output are not two independently issuable ALU ports. Exposing two independent operand/result paths would be a different routing/resource contract.

A separate future option can expose those existing add and multiply circuits independently, without replicating their arithmetic. It needs two independent operand pairs, two returned-result/tag routes, and sufficient context read/write bandwidth or explicit arbitration. With a single writeback route the apparent gain can disappear. Even granting free dual issue and writeback, the all-long resource floor is max(9*N add, 12*N mul)=12*N; M128 ideal Dense plus this floor is 2,322,432 cycles, full utilization at most 63.2296%. The analogous conditional M1024 upper bound is 65.0814%. This is a distinct optimistic port-change condition, not throughput of the existing ALU interface or the proposed minimal single-issue model.

For E elements, E_long nonsaturated elements, and sixteen such ALU ports:

`ALU service slots >= ceil((4*E + 17*E_long)/16)`

The two saved M128 arrays have E_long=E=1,146,880, hence 1,505,280 ALU service slots. This arithmetic lower bound ignores all wrapper bubbles, conversions, division, memory and synchronization. Together with current serialized-owner ideal Dense, it bounds M128 complete utilization by 49.4840%. It is not a prediction that this bound is attainable.

If divider initiation intervals for accepted jobs are known, each lane also needs the sum of those intervals, subject to endpoint conventions. For a hypothetical common divider interval d, the aggregate service lower bound is max(21*N, d*N) in the all-long case, N=E/16; dependencies and startup/drain add cost. d is deliberately UNBOUND. Do not substitute an invented 20/25/27-cycle divider or infer II from latency. The existing FSM's four-state lower bound does not establish the raw divider's precise timing after that FSM is redesigned.

## Context and return ledger

A concrete conservative context schema per lane can use five FP32 fields (gate, up, fraction, work0, work1), UInt8 k, UInt5 micro-PC, valid, error, five raw primitive flag bits and flags-valid: 181 logical bits. work0/work1 alternate scaled input, Horner/product, exp/denominator and inverse/final products. No independent copy of every expression is required.

One context's payload can be mapped onto existing outer gate/up registers and the existing core fraction/Horner/product/k registers. That is an explicit proposed lifetime mapping, not a synthesis proof. Each additional sixteen-lane context costs 2,896 logical register bits unless an existing buffer is explicitly leased. A 20-bit batch ordinal per extra vector context is sufficient for M1024's 573,440 vector groups.

The divider has no output-ready input. Every output-valid pulse must be captured or committed immediately. Two valid implementation choices are:

1. Use a single context-table write route and suppress that cycle's ALU issue whenever a divider result owns writeback. The software model must count the resulting bubbles.
2. Add a one-entry divider result holding register per lane, containing value32, flags5, valid1 and context-tag ceil(log2(C)); commit it through the same write route later. Reserve its credit before issuing the divider, and do not issue a new divide until that reservation is safe.

Per-lane divider ownership additionally needs valid1 + ceil(log2(C)) tag bits. A plain C=2 design therefore has the following explicitly additional logical state: one extra context 2,896 bits; batch ordinal20; divider owner32; optional result holding624. Total with holding registers: 3,572 bits (446.5 bytes of logical state). C=4 totals 9,436 bits (1,179.5 bytes) by the same schema. These are proposed register counts, not SRAM allocation, gate area or a minimum proof. They exclude new scheduler/address/control logic and any extra pipeline stages.

OverlappedSilu already has two 128B input entries and two 64B output entries (384B), but they cannot simultaneously remain memory-overlap queues and be counted again as context storage. Non-overlapped and overlapped elaborations have different available buffering. Any zero-new-storage claim must enumerate an actual replacement/lifetime plan, including the loss of queue capacity. Existing core registers not used by a proposed mapping may reduce added state, but that has not been proven here.

## RNE, errors and completion

Keep per-element dependencies and all existing rounding points: each polynomial Mul result must feed its matching Add; each Add feeds the next Mul. Preserve original coefficients, scale, UInt8 k construction, exponent restoration and |gate|>=80 saturation. An unrolled degree-7 spatial pipeline with extra operator instances is outside this fixed-unit proposal; temporal interleaving only fills idle slots of existing units.

Match the original error policy at semantic primitive boundaries. Add/Mul outside ExpNegative reject NV/DZ/OF/UF and nonfinite inputs/results, but NX alone is accepted. Div retains UF rejection. Existing ExpNegative ignores its internal ALU flags; blanket propagation of those flags would change the policy. Mask inactive work and retain the sign handling and three separate final Mul operations. Errors must stop new work, drain accepted divider results and pending stores, preserve acknowledged-byte accounting, then finish with failure. Store outputs in original batch order and hold them under backpressure; a ready later context cannot bypass an unready earlier output.

## Minimum software-cycle-model contract

1. Input: immutable saved gate/up manifests plus a resource profile. Default remains current wrapper scheduling. The proposed scheduler must require an explicit separate profile.
2. Emit each lane's ordered micro-operations, including group/context identity, named result slot, predecessor IDs, rounding boundary and error-policy class. No numerical forward is needed to construct this dependency graph.
3. Resources: sixteen single-issue ALU ports, sixteen converters, sixteen nonpipelined dividers, C lane contexts, one chosen writeback route per lane, and explicit input/output queue credits. No extra units or ports may appear implicitly.
4. Require ALU/converter latency and initiation interval plus actual divider input-ready/output-valid timing or a clearly conditional divider timing profile. If missing, report resource lower bounds and unbound parameters; do not return complete predicted cycles.
5. Reserve a divider destination before issue. Route its return by the captured context tag. Arbitrate ALU and divider writeback according to the selected implementation. Schedule only ready micro-ops; use oldest-ready policy initially, without speculative reordering inside one element.
6. Stop only after every accepted vector has produced exactly one ordered terminal result and all writes/queues/dividers drain. Keep memory and owner-level overlap absent in the first model.
7. Mechanical acceptance: no lane/resource double booking; stable stalled outputs; exactly one consume per divider return; all 21 non-saturated ALU nodes preserved; no context reuse before result retirement; correct all-short/mixed/all-long branch counts; bounded queues under result stalls; poison drains without success publication. Compare a later numeric oracle's intermediate bits/flags at each original primitive boundary, including signed zero, subnormals and exp threshold cases.

Adding a LUT or changing exp approximation is an unapproved numerical-policy alternative, not part of this proposal.
