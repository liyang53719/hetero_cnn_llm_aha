# Independent complete phase3/4 transpose source

This batch adds GdnChunkTransposeOwner only, without editing any original owner, shared service, Host, public M1/recurrent entry, or frozen candidate. One private job executes K→KT followed by KE→KET for one context/head/chunk. Each full64x128→128x64 transpose uses one1024B payload tile,512 reads and512 successful write ACKs. All64 padded rows are processed even for M16. No arithmetic is issued; all finite FP32 words, including signed zeros and exact subnormals, retain their bits. NaN/Inf inputs are rejected per the pinned software read contract.

The accepted prior phase2 result must have full identity/context, exact counters and valid private decay. The owner generates phase3 completion from its own finalACK; phase4 cannot start earlier. The phase3 checkpoint remains successful if phase4 later fails, while the aggregate result and forwarded decay are invalid. Only both full phases succeeding with zero outstanding requests produce overall completion. This is private scratch staging, not persistent state/root/generation publication.

Receipt provenance and exclusive stable input/root ownership are scheduler obligations, not implemented wiring. The trusted scheduler must retain the real successful phase2 result and its full prepared/phase1/initial-or-previous16+17 lineage. This standalone source does not establish those producers were run or connect them into Host. Private decay is forwarded only, never recalculated. No UT/dot/Matrix implementation is added.

## Proposed bounded controls

The test source supplies an explicit Python mirror of the seven-state protocol and independently checks full bitwise transpose/address formulas. All ACKs and read responses in that test are Python replacements. Source correspondence uses fixed raw bytes, with manifest/dependency pins checked before loading the model and again after tests; the model is compiled from verified bytes rather than imported through pyc. No original candidate module is imported, and no Scala/JVM/native/network/child process is run.

There are18 proposed unittest groups, including two full online Python trajectories (M16 cold head3/chunk0 and M128 warm head15/chunk1). The fixed command proposal is TEST_COMMAND.json. Root, after source review, may run exactly one target CPython3.12 batch with10s outer wall and CPU10/10, one CPU,256MiB address space,4MiB aggregate owned log allowance and1MiB per log. The author has not run it. File presence or source review does not grant execution authority. The root wrapper independently binds SOURCE_MANIFEST before and after because a manifest cannot hash itself.

Qualification at freeze: source and proposed tests only. No Scala compile, Chisel elaboration, actual memory handshake, RTL simulation, fullchunk, numerical validation, or fullblock utilization evidence. Any later result belongs to its independent receipt and does not rewrite this frozen historical statement.

## Resource and performance scope

The1024B bound is payload storage ONLY. Context, decay, status, counters, indexing and control require additional registers; no synthesis/resource allocation has been validated. The memory port is the existing single-outstanding64B protocol, not a burst/overlap architecture. There are2048 transactions per combined job,32768 read and32768 scratch-ACK bytes per phase. Cycles depend on actual request/response stalls; integer transaction counts are not measured cycles or complete-block throughput.

The existing Matrix path remains BF16-ingress/fused and is not proved equivalent to strictFP32 ascending separate Mul/Add chunk dots. The separate matrix-reuse audit and Loan3N versus3N−1 timing convention remain valid source-only analysis. No performance claim is improved by this bit transpose owner. Original public multi-token rejection and Host publication fences remain pinned and unchanged.
