# Quiescent Dense ports memo candidate

Only a scoped, read-only wrapper around the existing LoanDenseOwner instance's
ports method is introduced. No Dense/Tile/Host tick is replaced or skipped;
original clock, A begin_cycle, side effects, DMA, credits, responses and every
Memory/ACK handshake continue to execute. This does not claim hardware cycles
are shortened. It is reversible on ordinary and exceptional scope exit.

Memo eligibility requires unchanged exact owner/bank/tile identities, an active
A lease, entirely idle Dense/window/drain/seed/adapter states, all operand,
DMA, FIFO, accepted-write, seed and tile debts absent, no group, no poison/reset,
no live/sealed tile tags and no current A/B bank access. Otherwise the original
ports method runs immediately. Clock, Tile cycle, lease identity and policy
changes invalidate the cache. Original output dictionaries containing any
nonscalar value are never cached. Cached data is private/immutable and each call
receives a fresh dict. Statistics never contribute to original model counters.

Cold tests compare all original empty-edge events and side effects and inject
individual same-clock debts, reset/poison, state/policy/lease/clock changes,
external offers, SRAM access and scope exceptions. The actual bounded batch
has four fixed cases: original/memo two-tile runs and original/memo accepted
write-abort runs. All use real M16 pc0 Norm/ACK/publication and pc1 profiled
binding, the unchanged exact64 owner/library and original Memory/ACK. Each
edge's actual pending response, returned event and resulting clock/Host state
is recorded. Paired transcripts, complete output allocations, final protocol
accounting and failed locked/reset terminals must agree exactly.

No business weights, oracle/reference arithmetic, compilation, whole Q, M128,
fullblock or automatic retry. Same verified private small02 binary prerequisite
as the prior profile. Default/cold path reads no private work. Single batch:
20 CPU seconds, 2 GiB AS, 30 external wall seconds, observed 7 MiB stop/final
8 MiB output. Observation is not a filesystem quota. Per-call software timers
exclude transcript encoding; full-loop timings include observer work. Both are
small local timing estimates, not hardware cycles or old-timeout stage proof.
DIAGNOSTIC_SOFTWARE_OWNER; hardware mapping NOT_IMPLEMENTED; performance NO_GO.

## Observed local differential result

All four fixed cases completed. The paired two-tile and accepted-write-abort
transcripts matched byte for byte across 15,622 and 7,924 observed edges,
respectively; full output allocations and terminal/accounting records matched.
No original tick was skipped.

The two-tile driver-call CPU measurement increased from 0.68347 seconds to
1.24396 seconds, a 1.820x slowdown. This single local observation includes
fine-grained timer effects and does not establish a statistical performance
bound. Correctness passed locally, but the memo is **not adopted**: its software
optimization verdict is **NO_GO**. This result does not locate the earlier
fullblock timeout stage. These observations were added after execution; the
executed source snapshots remain distinct from this documentation update.
