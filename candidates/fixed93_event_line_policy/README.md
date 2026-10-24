# Event-only owner-line observation policy

This is an independent source/synthetic candidate, not execution permission.
Policy: `event-only-owner-lines-v1`, layered on the unchanged
`tick-boundary-metadata-integrity-v1` and prior `op-evidence-boundary-v1`.
The predecessor and all prior actual/FAIL artifacts remain unchanged.

Only Attention's local listener changes. At construction, after the final memory
anchors have been found, an immutable exact CodeType-to-line table contains:
5 `_attention` hooks, 4 `_matrix_step` hooks, 3 `tick` hooks, 2 `_write` hooks.
Inside the same admitted live owner tick, with no sticky observation failure,
a normal non-hook line checks thread, exact owner and bounded ancestry (128),
including exact frame identity for tick itself, then returns without the prior
`_integrity` and `_line` dispatch. No shared dispatcher or other listener changes.

All 14 retained hooks execute the original full `_line` body. All four Matrix
hooks retain original context, opcode, column type/range/alignment and causal
coordinate checks. Six scalar caller anchors consume actual `_op` returns and
remain untouched. All call/return/exception/unknown events, outside-tick lines,
failed-state callbacks, tick full-boundary checks and final scope cleanup remain
unchanged. The original `_identity`, `_cheap_identity`, `_integrity`, numeric
field writes, events, fences, codec and scheduling code are byte-identical.

## Explicit integrity difference

This is NOT the predecessor's anti-tamper sampling contract. On skipped lines,
client/job/service/profile-object/Dense-binding checks and Matrix local/context
checks are no longer performed. A transient alteration restored before the next
applicable retained hook or event can escape detection. Persistent wrong Matrix
locals are rejected at their next applicable hook; a persistent service/ownership
change is rejected at the next retained identity point. Detection timing and
first-error ordering may differ. Thread, exact owner and active-frame ancestry
remain checked on each filtered callback. No claim covers adversarial replacement
of the observer itself or arbitrary asynchronous third-party code.

## Static consumer map, not a timing model

The four pinned source functions contain 193 executable body line positions:
60 + 12 + 117 + 4. Fourteen consume evidence; 179 do not. `_matrix_step` previously
performed local validation even on its eight non-hook positions, so these are not
called check-free. The current owner tick's top-level coordinates include 209
and 249 (not the historical draft's 207 and 246). Static positions are neither
runtime event counts nor a 193/14 speed ratio. There is no M128 time guarantee.

## Synthetic controls

`python -I -B tests.py --baseline PATH_TO_0526`
The test pins raw bytes, compiles complete modules without executing their
module top levels and invokes original observer/dispatcher CodeTypes with MOCK
owner/service/ABI/frame/sink objects. The new constructor's exact table AST is
executed, not the full production constructor. All 14 actual consumer bodies
run on valid synthetic locals and compare fields, presence, event payloads and
fences. Six scalar anchors retain all 40 synthetic field slots. The real shared
TraceDispatcher, original Wholeblock listener and a disclosed additional test
listener demonstrate unchanged other-listener line delivery. That third listener
is not a claim about the production subscriber set. Real Python trace events
exercise handled/unhandled exceptions and return cleanup.

Negative controls distinguish the intentional transient-local/cheap-identity
sampling difference from persistent rejection at hooks, wrong thread/owner/frame,
missing call/return, reentry, sticky error and out-of-tick behavior. The small CPU
comparison uses synthetic metadata and is not a real native ABI or M2 benchmark.
No DUT module import, model/native execution, full 48-domain run, wholeblock
completion, reference read, M128 numerical PASS or new actual authority follows.

A future actual assembly must separately pin and consume this policy in its
source, review, root ADMISSION and result. Old 0526 authority cannot authorize it.
