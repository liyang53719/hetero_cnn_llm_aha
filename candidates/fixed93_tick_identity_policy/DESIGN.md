# Proposed tick-boundary metadata-integrity contract

Status: SOURCE PROPOSAL. No source/actual qualification, authority or execution.
Baseline: successful 0503 callback-local frame-code cache observer. The original
0417/0503 same-live M2 output equivalence does not authorize this new policy.

## Purpose and unchanged evidence

Policy ID proposed: `tick-boundary-metadata-integrity-v1`.
Only the observer's repeated ABI/profile attestation strategy changes. Numerical
operations, owner/service calls, native configuration, original source, dispatcher,
all fourteen line probes, six scalar consumers, exp primitive order, sixteen
arrays/presence, forty-eight event domains, FIFO/tag/epoch/order/debt fences and
codec records remain unchanged. No model call is replaced or repeated. Existing
`op-evidence-boundary-v1` exemption for nonconsumer `_op` normal call/return stays
explicit; it is not silently expanded.

## Exact implementation boundary

Only the Attention observer changes. Wholeblock `_observe` already returns for
owner_tick as a support anchor, so it is not used for the new boundary. Preserve
original `_identity()` byte-for-byte as the full check. Introduce a separate cheap
check copied from its dynamic ownership requirements, excluding only the profile
value deep snapshot and 33-native ABI snapshot comparisons.

Always retained for previously full-checked callbacks:
- Same thread; same owner matrix/scalar, loaded library and accumulator address.
- Same profile object, Dense role binding keys and bound object identities.
- Accepted Job object identity when established.
- Exact Fixed93 client type, packed/legacy client types and owner/service links;
  original client-identity initialization and no-replacement rule.
- Original method-specific self/client/operation/context and all semantic checks.

Full old `_identity()` runs:
1. Original observer `_validate`, before observation and after it; original source,
   loaded closure, native-file and instrumentation rehashes remain unchanged.
2. Every original owner.tick call, before setting the active tick frame ID.
3. Every original owner.tick return, including exceptional return None, before
   the finally-clearing of that ID and before `_tick` can accept terminal/disarm observation.
4. First `_attention` call before the original `_start`, to capture newly created job/client bindings.
5. Every observed exception (including generator control exceptions, conservatively
   retaining the old exception path), and every callback outside a proven tick.

Only normal retained callbacks while that exact tick is open use the cheap check.
A bounded 128-frame f_back walk matches the live tick ID without reading ancestor
f_code. An unrelated callback or excessive depth fails, never assumes membership.
Unknown events and every callback after a latched failure retain the full check.
The existing no-evidence BF `_op` normal-call/return shortcut remains unchanged.
No shared dispatcher, line enable mask, owner tick body or service body changes.
The f_code value remains callback-local, never cached across callbacks.

Maintain one bounded active frame ID, not a frame object or history. Exact tick
code and `self is owner` are checked at both boundaries; nested/reentered ticks,
return without matching entry, and observation close with an open tick fail
closed. A tick-return check precedes event dispatch and terminal disarm. Any
observer rejection remains caught by the existing latch and cannot replace DUT
returns/exceptions. If a failed full check leaves an open tick, completeness is
already false; no automatic repair/retry or successful seal is permitted. Matching
returns clear the scope in finally, including failures and early terminal paths.
Observation close with an open scope latches failure, clears it and still performs
the original validation and stream close. No error is cleared.

Finite diagnostic counters may report full-check boundaries and cheap callbacks
outside the event stream. They are not model events or hardware cycle counters.
No new per-callback log, source reconstruction, fallback value or sampling is added.

## Explicitly weaker and retained threat boundaries

This is NOT observational-integrity equivalence with the old every-callback
contract. A profile field or native function/class/signature may change and be
restored entirely inside a tick, without reaching an exception/full boundary,
and no longer be detected. Persistent drift at tick exit, a subsequent outside
callback, exception or final validation remains a rejection. Same-tick changes
to cheap ownership fields remain checked at the original callback locations.
Source-file hashes before/after and loaded-code checks are retained, but are not
proof of absence of all transient memory/code mutation. Combined independent
faults may have a different first diagnostic. No hostile arbitrary-Python/native
in-process tampering guarantee, hermetic proof or actual FENV flags claim is added.

## Minimal differential gates before a new single-arm actual

A. Pure source and real-TraceDispatcher synthetic controls:
- Original full `_identity` and every evidence-producing helper byte/AST unchanged.
- Tick entry/exit full checks, inner ordinary callbacks cheap, outside callbacks
  full, and all exception events full; exact counters prove selection.
- Wrong owner/thread/client/job/binding identity on inner callbacks still latches.
- Persistent ABI/profile drift at tick return rejects; same-tick mutate/restore
  deliberately passes the new policy while old policy rejects, explicitly labeled.
- Exception original type/object/return flow, handled exception resume state,
  abnormal return None, nested/missing tick boundary and terminal disarm handling.
- Same original dual subscribers, field values, events, order and all six scalar
  consumers; no sampler and no DUT/native execution in these tests.
- Cheap check speed can be measured synthetically only; not a M128 prediction.

B. New exact source/policy/manifest/ADMISSION binding:
- New policy file consumed by the actual gate, not merely listed as provenance.
- New observer own path/pin, original factory/dispatcher/helper/source mappings.
- Parent-only postseal comparison of one new successful M2 arm to the independently
  sealed 0503 or 0417 new arm; all fields/presence/output/transport/decoded event
  semantics, with the same explicit opaque-ID rules. No historical child input.
- One new root invocation only, no repeated old arm, no SIGPROF or cProfile.

Only after those gates and independent actual cleanup/equivalence review may the
M2 timing inform the next engineering decision. There is still no automatic M128
admission or 6600-second completion guarantee. If the remaining measured cost is
not compatible with the full workload, do not launch another long prefix merely
because this metadata-check count fell.
