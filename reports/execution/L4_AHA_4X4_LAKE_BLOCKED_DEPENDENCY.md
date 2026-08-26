# L4 production AHA 4x4 Lake topology audit

Status: `BLOCKED_DEPENDENCY`. L4 cannot PASS on the pinned generator.

Pinned AHA/Garnet uses a column layout with `mem_ratio=(1,N)`. A column is
Lake/MemCore only when its index modulo N selects the single memory position;
there is no independent `lake_memory_tiles` argument. The locked commits are
AHA `3b171e813bc5e399b22921c8df20fd4e889f1569` and Garnet
`6a8520cf7361693e9fc1fb3906df6b4f37268a49`; Docker digest is
`sha256:a8784f2cfe96609a7e4403c29f6a82bd00c882c8564ef747541f78be75fa2b2b`.

The existing 4x16, mem-ratio-4 baseline has one Lake column: 16 MemCore and 48
PE tiles. Exhaustive 4x4 enumeration shows:

- ratio 1: 16 Lake, 0 PE;
- ratio 2: 8 Lake, 8 PE;
- ratio 3 or 4: 4 Lake, 12 PE;
- larger ratios: 0 Lake, 16 PE.

Therefore no pinned-generator setting yields the required logical 4x4 compute
SFU with 16 Lake SRAM tiles. A ratio-1 all-memory array cannot map depthwise
compute; the 4x16 Gaussian baseline violates the frozen production geometry.
Per the approved failure policy neither is accepted as fallback.

Evidence: `scripts/audit_aha_4x4_lake_topology.py` and
`reports/execution/aha_4x4_lake_topology_result.json`.

Resolving L4 requires a generator extension/topology contract that decouples
Lake local-memory instances from PE tile placement, or a revised user-approved
geometry. This audit does not block independent L5 work.
