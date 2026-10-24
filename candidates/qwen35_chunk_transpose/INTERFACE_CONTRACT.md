# Private chunk phase3/4 transpose owner, source proposal

This independent owner performs the complete existing TransposeK then TransposeDecayedK phases for ONE accepted context/head/chunk. It neither implements a whole chunk nor changes Host, public M1, recurrent, Matrix, Vector, Scalar, or shared memory interfaces. No new arithmetic or module is instantiated. No test, compile, elaboration, or hardware execution is implied.

## Qualification and ownership

The private job carries the accepted GdnChunkJob, 16-bit head/chunk selectors, and the existing complete GdnChunkDerivedAndPairResult. Phase2 must be successful, drained, stageComplete, phase=2, match tag/generation/head/chunk, acknowledge exactly180224 scratch bytes and zero external output/state bytes, read235584 bytes, and report Exp2209/Add2144/Mul2560 accepted-and-returned counts. Its private decay must be valid, finite, and match the ENTIRE context plus head/chunk. This includes vectorPolicy=LegacyFatalUnderflow. The complete context is bound through the existing decay.context, not an invented field on a previous result.

As with prior independent owners, receipt provenance and the phase1/prepared/initial-or-previous16+17 chain are TRUSTED SCHEDULER obligations. A caller-declared receipt does not prove actual wiring or execution. The scheduler must retain the actual successful phase2 result and keep all source matrices, the accepted root snapshot, and five complete nonaliasing spans exclusively stable until this job and held done retire. The owner samples qualification once at job.fire. It does not authenticate receipts, lock global roots, or publish state/generation. Public and recurrent multi-token rejection stays unchanged.

Cold requires generation0 plus invalid committed state. Warm requires positive exact generation and exact stateIn root. Generation0xffffffff is rejected. Only M16 or M128,16heads,64rows/chunk,128columns,legacy policy. All five full spans are64B aligned, disjoint, and end<=2^56 using66-bit arithmetic, including unused cold stateIn. Last address end==2^56 is legal. M16 still transposes padded64rows from successful scratch; there is no prepared-input read and no external output write.

## Exact order, storage, and acceptance

Phase3: K offset36864 -> KT266240. Phase4: KE233472 -> KET299008, relative to the selected per-head/chunk base. Source64x128 row stride512B; destination128x64 row stride256B. One16x16 binary32 tile is16x512-bit registers=1024 payload bytes. Context, decay word, counters and control registers are additional, not hidden in this payload bound. There is no second tile, overlapping next-tile fetch, SRAM or arithmetic service.

For each phase, r=0,16,32,48 outer and c=0,16,...112 inner. Read all16 source rows (r+i,c) before any tile output; write destination(c+i,r), taking word i from each tile row. Only successful matching write ACK advances write index/tile/phase. Each phase has32tiles,512read requests/responses,512write requests/ACKs,32768read bytes and32768scratch ACK bytes. Phase4's first read occurs only after phase3's final matching successful ACK. Per-phase counters stay separate. The only accepted command runs both phases, so no external phase3 readiness flag can skip the ordering fence.

Every successful read checks all16 FP32 exponent fields and rejects NaN/Inf before storing the tile. This preserves model._read even though transpose does no arithmetic. Signed zeros, finite extremes and exact subnormals are copied BIT FOR BIT, with no float conversion. An invalid late tile read causes zero writes from that tile; earlier acknowledged tiles cannot be rolled back.

## Memory and terminal protocol

Use original64B MemoryRequest/Response, fullwrite mask, Cat(context.tag,sequence) tag, single outstanding request, separate issue/wait states. MemoryResponse has NO nbytes field; fixed64B width is the request ABI, not a response-length check. request.valid with !ready does not become outstanding; response.valid with !ready is not consumed. A zero-latency response must remain valid until wait.ready. Matching response tag is checked before error. Read errors do not count a successful read; a matching finite-check failure counts transport read bytes but cannot write/complete. Wrong-tag retains outstanding ambiguity; any failure has drained=false, resetRequired=true and eventually locked after held error result retirement. Failed write does not count its64B or advance. Recovery must coordinate owner AND shared transport drainage/reset; owner-only reset cannot certify old responses absent. Same-tag command reuse assumes the existing no-stale/single-response transport contract, not cross-job replay defense.

Held done freezes every field including cycles; job.ready and memory.valid remain false until done.fire. Success returns idle after done.fire; error returns locked. No arithmetic/persistent-root effects exist. phase3Complete can remain true if phase4 later fails; it means its512ACKs genuinely occurred. phase4Complete/stageComplete and forwarded decay.valid require BOTH complete phases and no outstanding request. Failure suppresses decay.valid and value. The scheduler retains original phase2 decay separately; no phase15 consumer is added here.

## Verification boundary

Next proposed tests are pure Python source/integer/bit-transpose and protocol-model controls. They are NOT Scala execution, real Decoupled ACKs, a numeric oracle, CHIRRTL, RTL, or complete chunk/whole-block utilization evidence. Existing strict-FP32 Matrix reuse mismatch and serial-Loan performance audit remains unresolved; no UT implementation is included.
