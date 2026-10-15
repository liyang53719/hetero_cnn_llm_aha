# One local idle-drain evaluation specialization

This opt-in software experiment removes only the first redundant `ports()`
evaluation in the original FfnDrain tick's empty loan branch. The original
FfnWindow tick, Tile tick, Dense clock, shared A begin-cycle and all background
service/credit paths still run on every modeled edge. It adds no arithmetic,
response cache, event jump or hardware-cycle reduction.

The exact branch requires the sole target owner to have its shared A loan,
canonical four loan/window arguments, idle control states, no accepted Dense,
window, drain, seed or tile debt, no active tile tags and no poison. The three
loan flags force the original first `drain_ready` to false; no drain is offered.
The returned event adds the same three drain fields to the exact original
FfnWindow call. Every unrecognized argument, state, event and debt falls back
to the original method. Original exception behavior is compared too.

## Explicit loaded-code boundary

`IdleDrainScope` temporarily replaces the shared dynamic FfnDrain class method.
It targets one exact public LoanDenseOwner by object identity. All other owners
receive the saved original call with unchanged arguments. This is a runtime
loaded-code change despite the published source files remaining byte-identical.
It is not covered by the prior whole-job source audit and is not a mainline
integration. Only a single-thread process with no concurrent model execution
is admitted. Canonical method identities, module/super globals, and runtime
code against unexecuted source compilation are checked; reentry and instance
method overrides are rejected. The original class method is restored in
`finally`, including exception and detected scope mutation. No port result is
retained. Any later adopted change would require a versioned, reviewed local
source patch rather than a long-lived class monkeypatch.

## Fixed validation

Cold tests use actual original owner/Banks/Tile objects. They compare empty
edges, every declared debt/state fallback, tile poison, direct forbidden
requests, idle-to-active real Job acceptance, accepted-read abort/drain,
late ACK poison/reset, malformed arguments, canonical authority and restoration.
They run both normally and with assertions disabled, without native arithmetic.

The separately approved one-shot small execution is four fixed cases: baseline
and specialization on identical synthetic M16 public Norm-to-Q input, each for
two exact64 tiles, plus baseline and specialization aborting after an accepted
write. The original actual Profiled Matrix binding, Memory/ACK, Host, exact64
arithmetic and terminal checks are unchanged. Complete edge records, complete
output allocations and all terminal/accounting state must compare exactly.
First-tile and two-tile timings are retained for the two-tile cases. All cases
share 20 CPU seconds, 30 wall seconds, 2 GiB address space and 8 MiB output.
The supervisor polls process-group CPU/output and clears the group on all exit
paths; the output stop threshold is not a filesystem hard quota. No retry or
reduced case selection is permitted after failure.

Driver-call timers exclude JSON/gzip observation; full-loop timing includes it
and scope setup. Baseline and specialization use identical observation hooks.
A single sample cannot establish statistical speedup or identify the old
full-run timeout stage. Software seconds are not hardware cycles. This does
not execute a full projection, full block, M128 prefill, RTL or CI, and does not
close any prior numerical failure. Detailed inputs, paths, hashes and traces
stay in private work output; only fixed aggregate results may be published.

Default entry is source-only and reports `NOT_EXECUTED`:

    python -B -m candidates.qwen2_idle_drain_candidate.check_small
    python -B -m unittest candidates.qwen2_idle_drain_candidate.test_cold
    python -B -O -m unittest candidates.qwen2_idle_drain_candidate.test_cold

## Observed result, added after the single execution

Both differential pairs passed. The two-tile and write-abort pairs respectively
had 15,622 and 7,924 byte-identical complete edge records, with identical full
output allocations and protocol terminals. No modeled clock edge was skipped.

The two-tile driver-call CPU time was 0.81749 seconds before and 0.78901 seconds
with the specialization, a 3.48% reduction. The write-abort time was 0.35156
seconds before and 0.42903 seconds with it, a 22.03% increase. These mixed,
single-observation results do not establish acceleration. Mainline adoption is
**NO_GO**. There was no repeat run, result selection or wrapper retuning. The
original execution used the pre-result README; this section is post-execution
documentation only and does not change that execution's source identity.
