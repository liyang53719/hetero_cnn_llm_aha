# Source-attested owner-frame routing

This independent source/synthetic candidate is based on the frozen 0549 Attention observer and cached Wholeblock dispatcher. It does not change those files or any actual run. It makes an explicit new observation integrity-sampling contract, not a claim of equivalent anti-tamper detection.

## Why this cut

The separately reviewed 0557 successful diagnostic M2 main loop supplied 1,461 bounded Python stack samples. Exact mutually exclusive leaves included Attention `_trace` 396, dispatcher `_dispatch` 262, three audit hooks 453, Wholeblock `_observe` 90 and `native_snapshot` 42. The raw report SHA-256 was `8092f6dd5ef975fd2dd050e987dee2d56fa0f32e19698a36cbf66a3bd138e601`. These are diagnostic sample counts, not exact CPU attribution, lossless physical timer ticks or M128 time predictions. No further profile is needed for this design.

The source-selected union has five permanently line-enabled codes. Four owner methods have 14 Attention evidence consumers, while Wholeblock immediately returns for those four SUPPORT codes. The fifth, `execute_silu`, has an independent actual line-396 consumer and remains wholly unchanged. A static count of body lines is not a dynamic speed ratio.

## Production delta

- `overlay/cached_wholeblock.py`: exact original delivery body moved to `_dispatch_code`, accepting the immutable CodeType. The global callback reads `frame.f_code` once and still performs all original delivery on every call. Register/unregister increment a generation. An opt-in binder proves the exact current two bound callbacks, immutable four-code/14-line map and Wholeblock SUPPORT mapping.
- Only after successful original call delivery does `_route_frame` create a per-live-segment local trace closure. It captures an integer frame id and immutable CodeType, not the frame or its locals. It caches the current tick identity proved by the Attention callback.
- A non-hook line can return that same local callback without reading `f_code`, locals or ancestors and without either listener. Before doing so it checks the same frame id; current tick and live/error states; registry identity, generation, size and both tuple identities; current immutable hook map and Wholeblock SUPPORT mapping.
- Hooks and every non-line event execute the unchanged original delivery body. An exception forces its next line through original delivery. A return always expires the closure in `finally`, including generator yield. Resume calls create fresh segments. Return callback values are not relied on to expire a generator segment.
- Any route invalidation permanently expires the local segment and uses the original dispatcher. An extra/replaced listener is never silently skipped. Direct dictionary replacement of an entry is detected even without generation change.
- `overlay/narrow_fullblock_attention.py`: only `__enter__` adds the explicit bind call after original listener registration. All numerical/event/field helpers and original `_identity`, `_integrity`, `_trace`, scope close and poison behavior are byte-identical.

## Detection differences and preserved boundaries

`POLICY.json` is required, not an informational alias of old authority. On skipped off-hook lines, the predecessor's per-line thread, owner, locals and ancestor sampling is omitted. Such changes must persist to an applicable original call, evidence/control or return/exception boundary to be detected. Transient changes restored between boundaries may escape and errors may be delayed. This is a deliberate contract change to instrumentation-only protections, not a change to actual model arithmetic, schedule, cache events or record values.

All 14 evidence hooks, six scalar-return consumers, normal control events, handled-exception recovery and original scope/terminal failure paths remain. The 0325 no-evidence `_op` policy is not broadened. SiLU and all normally line-disabled codes use the original path, including temporary exception-resume lines. Wholeblock's other subscriber routes are not weakened.

## Validation boundary

Tests use exact source-compiled dispatcher and Wholeblock callback CodeTypes with explicitly synthetic owner methods and a MOCK Attention consumer. No DUT imports, native library, runtime initialization, source/data preflight, reference payload or historical stream is loaded. Real `sys.settrace` exercises Python generator call/yield/send/throw/close and local callback lifetime. Source comparisons separately show preservation of the original Attention helpers and original dispatcher delivery body. Synthetic mock field/event agreement does not mean all 48 real domains ran.

A new standalone policy/source review is required. Any later M2 integration must honestly pin both new module files and the policy, preserve source-specific factory binding and use a new authority. No actual execution, fullblock numerical PASS, runtime or time-budget qualification is conferred by this package.
