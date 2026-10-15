# M16 full-stage software cost diagnostic

This is a new, bounded M16 diagnostic of the existing public 21-command path.
It does not certify M128 prefill, current Chisel correspondence, RTL numerical
acceptance, or the 80/90% hardware utilization goals. The exact64 projection
owner remains a diagnostic software implementation. Neither the slower ports
memo nor the mixed-result idle-drain wrapper is enabled.

The purpose is to observe representative stage costs, rather than infer the
last stage of the earlier 3300-second M128 budget failure. Public completion
counts are separate from timed owner groups: public PCs 10–12 share Attention,
and PCs 16–18 share the interleaved FFN owner group. Their group elapsed times
must not be duplicated into 21 supposedly additive stage measurements.

## Fixed geometry and arithmetic

All original arithmetic and accepted Memory/ACK protocols remain required.
M16 uses 16 active rows, but the retained tail Matrix executes its physical
128-row shapes. Useful work and physical issued work are reported separately;
M128 costs cannot simply be divided by eight. The fixed physical workspace and
full cos/sin RoPE storage layout are retained. Input rows may be selected from
the verified source input; old M128 output tensors are not an M16 oracle.

A fresh official reference executes the original arithmetic at actual M16
geometry after the model completes and seals its outputs. Its comparisons
reuse the original numerical metric and threshold semantics. A causal-prefix
relationship does not establish cross-shape backend bit identity. Reference
completion does not confer a new formal platform contract or hardware PASS.

## Order, limits, and durable evidence

Default module entry points are NOT_EXECUTED. The fixed `cost01` namespace is
single-use. Run the model phase first; reference execution is allowed only
after a successful model supervisor receipt and the model's own complete seal.
A model failure leaves the reference NOT_RUN; there is no retry or third phase.

- Model: 1200 CPU seconds, 1260 outer wall seconds, 4 GiB address space.
- Reference: 60 CPU seconds, 90 outer wall seconds, 4 GiB address space.
- Reference and model outputs, logs and receipts share 96 MiB; the supervisor
  observes a 95 MiB stop threshold. This is not a filesystem aggregate quota.
- Group CPU/RSS and output sizes are sampled. The parent reserves cleanup time
  inside the wall limits and applies per-child CPU/AS/file-size limits.
- Each real stage BEGIN/END/FAIL is immediately flushed and fsynced. The parent
  also atomically replaces a fixed-schema heartbeat every five seconds.
- Catchable interruption cleans the child process group. SIGKILL or destruction
  of the entire environment cannot guarantee a final receipt; existing durable
  stage records remain observations rather than acceptance evidence.

Only fixed stage/status enums, bounded counters, and finite timing/resource
numbers are eligible for public summaries. Inputs, weights, arrays, private
receipts, detailed paths and raw exception/log text stay local. Numerical
comparisons require the complete sealed model output; a partial trace cannot
substitute for missing final results. No business execution has yet been
performed for this package.
