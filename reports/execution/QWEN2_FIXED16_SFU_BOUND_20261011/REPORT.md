# Fixed-16 SFU SiLU lower-bound audit

This is a source/FSM lower bound plus a small NumPy read of two existing M128 gate arrays. It is not an RTL measurement, a new forward, numerical acceptance, or a full-cycle prediction. Full-file source hashes and both input receipts/hashes are in RESULT.json. No production source was changed.

## Strict source bound

VectorSilu.scala:34 instantiates sixteen BlockScalarFloat cores. Its six serial phases are ExpNegative, Add, Div and three Mul operations (lines 43–65). Both VectorSiluOwner and OverlappedSiluOwner use that same unit; the selection is exclusive (OverlappedSilu.scala:108–112).

BlockFloat.scala:55–108 gives minimum request intervals of 3 cycles for Add/Mul, 3 for a saturated ExpNegative, and 20 for a nonsaturated ExpNegative. Div must visit idle acceptance, divIssue, divWait and done; its interval is at least 4, without assuming the iterative divider's exact latency. The vector wrapper adds its outer accept/return transitions.

For one successful nonsaturated group, earliest edges are: vector request E0; exp request E1, exp result E20; Add E21→E23; Div E24→E27 or later; three Mul phases E28→E30, E31→E33, E34→E36; vector result E37; next vector request E38. An all-saturated group can be no faster than II21.

For N consecutive 16-element groups and L groups containing at least one finite |gate|<80, the edge span from first vector request.fire to final result.fire is at least:

`21*N + 17*L - 1`

Errors can shorten execution but do not constitute successful complete-block performance. Finite gate statistics alone do not prove the legacy scalar error policy succeeds.

## Two saved M128 distributions

- Original ordered software-recipe gate: 1,146,880 finite FP32 values, max |gate|=5.609712600708008. All 71,680 groups contain nonsaturated values; in fact every element has |gate|<80. Gate SHA256: 288123c170c85a5b47d0d03a0f3c93ff7fdbe6c8014bdc820e910c82a870efb5.
- Unapproved BF16-materialization-v1 candidate gate: same count, max |gate|=6.0. All 71,680 groups and all elements are nonsaturated. Gate SHA256: b1a3481746af6b2f584afe2456bce5c75edbe011904473c7dfb59de2e65980a6.

Both hashes match their saved RESULT.json entries. They remain distinct diagnostic sources; neither is RTL execution evidence, and the v1 candidate must not be presented as v0 hardware input evidence.

## Implication for 80%

Use useful MAC/(4096 × complete cycles), with all seven Dense matrices and causal QK/PV in the numerator. Current Kernel active/mode serializes Dense and Activation (QwenOwnerProtocol.scala:88–115, 288–300).

| Condition | M128 | M1024 |
|---|---:|---:|
| 80% complete-cycle budget | 1,835,580 | 15,114,720 |
| Ideal Dense arithmetic | 1,462,272 | 11,698,176 |
| Universal successful SiLU bound, even all exp saturated | 1,505,279 | 12,042,239 |
| Ideal Dense + universal SiLU | 2,967,551 | 23,740,415 |
| Full utilization upper bound under that sum | 49.4840% | 50.9333% |

For either observed M128 gate distribution, SiLU alone requires at least 2,723,839 cycles. That alone caps full utilization at 53.9116%, even if Dense could perfectly overlap it. Under the current serialized owners, ideal Dense + this SiLU bound is 4,186,111 cycles, capping full utilization at 35.0794%. Every other block stage and all memory costs are omitted.

No M1024 distribution was read. An all-nonsaturated M1024 scenario is recorded only conditionally in JSON.

Even a more permissive redesign that makes all four Add/Mul phases and wrapper overhead free still needs one ExpNegative and one Div per element on the existing sixteen nonpipelined scalar services. Their universal minimum service work is (3+4)*M*8960/16 minus one endpoint cycle. With current Dense/Activation serialization and ideal Dense, this alone caps complete utilization at 74.7679%/76.9576% for M128/M1024. This relaxed bound assumes unchanged BlockScalarFloat FSMs/ports; it is not a theorem about arbitrary future 16-SFU implementations or changed owner overlap.

No exp replacement, reassociation, underflow-policy relaxation, extra SFUs or divider-latency estimate is used.
