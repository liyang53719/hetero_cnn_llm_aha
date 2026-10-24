# Normal non-evidence `_op` boundary policy v1

Status: proposed source/synthetic-only observation contract. No execution authority,
no assembled candidate, no inherited native, startup, M128 or full-block PASS.
This proposal is based on the current full-block observer, not on the independent
expected-ABI-cache experiment. The original full `_identity` is unchanged.

## Exact selection rule

Existing admitted-code, scalar/exp, disarmed and failed-stream gates run first.
Within the original exception-latching `try`, only an event satisfying ALL of:

1. `frame.f_code is self.codes['_op']`;
2. event is normal `call` or `return`;
3. `frame.f_back is None` OR its code is not `self.codes['_attention']`;

uses the light path. It checks the original observation thread and exact owner
instance, then returns the original callback. It does not call `_identity`.
All exceptions, lines, unknown event names, `_attention`-caller `_op` callbacks,
and all other admitted codes continue through the original full path. Wrong
thread/owner errors are latched by the same original handler, not injected into
the observed program. Existing disarmed/failed-stream behavior is unchanged.

| Code / caller / event | Attention listener | Other listeners |
|---|---|---|
| `_op`, non-`_attention` or no caller, normal call/return | exact code + thread + owner; no full ABI/profile check | unchanged |
| `_op`, any caller, exception | original full identity + original exception observation/poison | unchanged |
| `_op`, `_attention` caller, call/return | original full identity + six scalar-anchor return consumers | unchanged |
| `_op`, line/resume line or other event | original full path | unchanged |
| all other admitted codes/events | original full path | unchanged |

The shared `TraceDispatcher` and whole-block subscriber are byte-for-byte
unchanged. Listener return values do not alter dispatcher delivery. In actual
M128 dispatch, `_op` already has line tracing disabled, except the existing
handled-exception resume-line mechanism. This proposal claims no `_op` line-event
saving. Four line-traced owner methods and all their current identity checks are
unchanged.

## Evidence preserved

The old `_scalar` immediately returns without emitting anything when its direct
caller is not `_attention`; the old normal call branch for `_op` also emits
nothing. Therefore the selected successful callbacks contribute neither fields
nor event records. The 16 field definitions, all 48 event domains, six scalar
anchors, 14 evidence-line anchors, 17/1 exp primitive graph, causal-key counts,
normalization 1/use 8/reuse 7, lease/ACK/debt/fence and terminal checks are not
edited. Array values and actual event order are still read from the same original
operations. No DUT operation is repeated, replaced, recomputed or skipped.

This is a source argument plus bounded synthetic comparison, NOT proof that all
48 domains have executed, nor a new numerical acceptance result. Current event
wire schema stays v2. Actual use requires a newly source-pinned observation
policy identity in the candidate's reviewed contract/admission, and a validator
that does not confuse the old stronger cadence with this policy. This standalone
patch does not silently claim either candidate or run admission.

## Deliberate detection difference

Old policy checked the complete service/ABI/profile/client binding inventory at
every selected normal callback. New policy does not promise to detect temporary
ABI/profile/service/client drift appearing only at one or both filtered callbacks
and restored before the next retained full-check boundary. This includes the
period around a no-evidence scalar operation. Such drift is not certified safe
or equivalent: it is outside the new transient-tamper detection claim.

Persistent drift that reaches a retained boundary still meets the original full
check. Exceptions still take the original full-check/observation path. Owner and
thread mismatch at the filtered callbacks still fail. If an owner mismatch and
ABI/profile drift occur together, both versions reject but first-error text can
differ because the new light owner check precedes the omitted inventory check.
This is not a promise of identical diagnostic priority under combined tampering.
Source hashes, loaded
source guards, initial/final checks, actual record/array sealing and independent
numerical validation remain required, not replaced by this policy. Synthetic
counterexamples must demonstrate the declared old/new transient-detection
non-equivalence rather than call it a regression-free anti-tamper optimization.

## Performance qualification

The fixed M128 source has at least 39,124,992 relevant BF16 ingress/output `_op`
invocations and 78,249,984 normal call/return callbacks. This is a count bound,
not elapsed-time proof. Compare old/new callback cost with the same fixture,
Python, CPU and repetitions. Do not use the independent pure-class ABI-cache
benchmark as a native-class timing comparison. Remaining per-line checks, real
native arithmetic, stream encoding/I/O, prefix and tail costs are not eliminated;
a microbenchmark does not guarantee completion within the frozen 6600 s budget.

## Test and integration boundaries

Small tests use synthetic operations/frames and explicitly mocked owner/service
state. They load exact original compiled dispatcher and subscriber code without
DUT imports or foreign arithmetic. They cover record/field equality on retained
routes, second-subscriber delivery, original exception propagation, resume-line
cleanup, wrong owner/thread, caller/code distinctions, original short circuits,
and transient versus persistent drift. Source AST checks establish that only
`_trace` changed and the insertion removed restores the exact old function.

Before actual use: independent review; new nested/top source pins and policy
identity; integration-specific cold checks; credible aggregate timing assessment;
separate root run admission. No old result, failed prefix or unknown run is a
substitute for one complete same-live M128 block.

### Minimum successor wiring, not yet implemented here

The policy file must be an active preparation pin, not an unused historical
artifact. A new current contract, independent source/cold receipt and new root
ADMISSION must agree on this exact policy identity and file SHA. The actual gate
must require that binding and reject omission, the old per-event policy or a
mixed source manifest. The actual result must identify the consumed policy.
These metadata/gate changes are a separate reviewed successor; this standalone
module and its synthetic tests do not implement them or authorize execution.
