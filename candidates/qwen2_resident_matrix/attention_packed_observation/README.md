# Pinned packed Attention observation, preparation only

This separate adapter preserves the original ten numerical fields, their exact
word layouts and causal presence masks. It observes real `PackedSchedule.run`
locals, actual `AttentionOwner._op` return words (legacy_scalar policy), selected
Matrix results and attempted store words. It calls no arithmetic service and
never reads either independent reference. Original tolerances and comparison
functions are unchanged; this package does not grant full Public admission.

Packed QK maps 16 keys to selected 16-stripe lanes. Packed PV captures six heads
at once. Each causal probability is observed once, not the legacy eight column
repeats. Each normalizer is observed once per head/query, rather than
`8*(query+1)` times. This explicit frequency contract does not fabricate eight
observations. All ten numerical values/presence masks retain their legacy shape.
Future keys remain absent with sentinel `0xa5963cc3`.

Inline dot-BF16 and pre-BF16 probability values come only from actual source-bound
scalar return events. Their operation order, arguments, owner/frame identity and
packed BF16 packet are cross-checked. Missing, repeated, interrupted or foreign
capture sequences fail closed. No recomputation fills missing intermediates.

The source-only composition binds the complete M16 preparation closure, original
observer code helpers and this adapter. It verifies loaded methods/imports and
exact OfficialAttentionOwner/ProfiledMatrixService/ScalarService types. The
schedule may be installed inside the original Public Attention helper; the
observer binds its exact instance only at accepted job_fire, before any observed
arithmetic. The adapter rejects CPython optimization mode in production.

The accepted original terminal, tag, write-byte/ACK fence, idle/unpoisoned owner,
released Matrix/scalar, retired client, and empty memory/scratch/output debts are
all required for COMPLETE_OWNER_OBSERVATION_NOT_NATIVE_ACCEPTED. Capture completion
never means numerical PASS, native acceptance, full29, publication, RTL or MAC
utilization acceptance. Summary output is hashes, shapes and counts only.
`save()` explicitly writes private activation files for the existing comparison
interface; never commit/upload those files. There are no model payloads here.

Cold tests compare deterministic synthetic packed bytes/masks against the legacy
observer layout at M1/M2/M16, exercise the real unchanged schedule at M1/M2 and the
composed M16 schedule with synthetic services, and reject missing/duplicate/future
fields. Production source/type, partial-entry cleanup, foreign callback/event
ownership, interruption and retirement gate tests block CDLL and compilation.
These tests establish capture plumbing, not numerical accuracy of a model.
