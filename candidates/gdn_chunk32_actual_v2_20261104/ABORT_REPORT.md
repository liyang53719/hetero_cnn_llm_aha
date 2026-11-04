# Execute32 explicit abort/cancellation candidate

Status: SOURCE PROPOSAL + BOUNDED PURE PROTOCOL REGRESSIONS ONLY. Not compiled, elaborated, RTL simulated, synthesized, published, or admitted. Full original build 97358 remains UNKNOWN; no reused PASS and no resource borrowing. R1/R2 sources are untouched.

## Failure contract

The opt-in Execute32 path gets a registered abort input and two explicit unaccepted-offer cancellation handshakes. The raw leaf holds valid and payload through cancellation ACK. Wiring either acknowledges an offer never presented to the receiver, or forwards cancel to the actual receiver and waits for its ACK. The receiver masks that RR input and forces ready low on the ACK cycle, so ACK and request.fire are mutually exclusive. Both hold bits and the leaf issue state retire on the same edge. Cancellation increments no accepted, issued, returned, read/write, grant, or successful-retirement count.

Already-accepted memory/vector work cannot cancel. Its retained tag/owner and all accounting survive abort. Actual matching responses must return through the existing router to repay debt. Matching error responses repay debt but produce failure. Missing responses retain debt and resetRequired indefinitely: no watchdog timeout or reset waiver is invented. Unmatched vector/leaf returns quarantine instead of clearing debt or offering a false drained terminal.

In the opt-in shared hub, wrong transport tags now quarantine without rewriting the return into originalTag and delivering it as a purported matching error. The retained request/accepted count remain. Once quarantine is set, later responses are not consumed. This is safe blocked recovery, not bounded successful drain.

Abort reflection is entirely RegNext to break adapter raw-valid/shape/count fault feedback. Requests exposed in that one-cycle window can subsequently cancel explicitly, so neither fresh hidden nor already-held offers deadlock merely because adapter admission has poisoned.

The leaf reports one held failure receipt only after debts are clear and no quarantine remains. The actual coordinator consumes the exact identity receipt, counts partial Execute32 acknowledged traffic once, waits for the existing fabric quiescence predicate, and captures its single error terminal. Its existing poison/locked state and Guard/final-publication veto remain. No success permit or staged-success receipt is fabricated.

## Scope and compatibility

Actual physical mapping is verified in source: Execute memory ordinal4 plus wiring offset12 is SharedMemoryArbiter client16. Only that client's offered requests have cancel ports. The adapter cancel port only covers the Chunk32 raw ingress; accepted bank ingress and bank-held result are untouched. Both arbiters capture payload/owner only on ingress fire, and are non-locking RR arbiters. No physical memory request or bank request is withdrawn by cancel.

Default constructors retain legacy behavior: cancellationClient=-1, enableChunk32Cancel=false, enableExecute32Abort=false. Top enables them only with enableChunk32. Legacy execute wrapper ties cancel intent false. In opt-in mode the hub's strict wrong-transport-tag quarantine applies to all its accepted clients, not solely client16, because unknown transport replies cannot safely be credited to anyone; this deliberately changes opt-in error behavior, not legacy/default behavior. Other leaves do not gain abort state machines.

This is NOT a complete fault-abort closure for RawPrep, state/load/derived/transpose owners, Guard context quarantine, unexpected terminals, or malicious route/identity faults. Those may remain blocked. A global finite bound cannot be claimed unless external memory/service responses, terminal readiness, Guard identity stability, and the other clients' drain are guaranteed. Under those conditions the control path ends after at most the outstanding operation's real return plus local cancellation/leaf/coordinator/retirement clock steps. The pure model checks finite delays, not a native-RTL cycle bound.

No arithmetic ordering, payload width, bank count, physical primitive, accepted operation identity, or success count equation is changed. The leaf retains three 1024-bit payload registers. New storage is only abort/quarantine/offer control state and registered abort reflection.

## Inspection and regressions

Inspected actual Guard, RawPrep, Coordinator, Wiring, Adapter, SharedMemoryArbiter, leaf, selected wrapper, Collection, Kernel and Top. Guard deliberately refuses unknown/context-mismatched terminals. RawPrep already has fault-aware held offers, but lacks this new receiver cancellation extension. Existing coordinator poisonWait preserves pending identity; existing adapter drains accepted captured bank offers/results after poison while rejecting fresh acceptance. This was the original held-offer deadlock boundary.

19 standard-library Python tests pass normally and under python -O. Cases cover fresh/held cancellation, ready/ACK exclusion, poisoned receiver, held stability, accepted-debt preservation, delayed/missing/wrong returns, same-cycle fault/return, prior return followed by blocked offer, repeated abort, terminal backpressure/exactly-once receipt, normal operation conservation, exhaustive bounded delay combinations, and source binding/constructor checks. The model is deliberately labeled pure reference protocol, not execution of the Scala FSM. Source checks are lexical pins, not elaboration proofs.

Independent review identified and this revision fixes: combinational abort feedback, unintended default-legacy coordinator accounting change, and wrong-tag retagged debt repayment. Parent confirmed independent recheck before this source integration. Native verification remains pending.

## Files

source/ has 11 changed/new exact Scala overlays. MANIFEST.json records original upstream paths and SHA-256 per before/after file. review.patch contains the complete unified delta. implement.py deterministically regenerates the overlays from unchanged frozen R2 + original base. test_abort_contract.py and TEST_NORMAL.log / TEST_OPTIMIZED.log contain bounded validation.
