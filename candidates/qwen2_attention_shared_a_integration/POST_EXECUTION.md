# Post-execution result and safety projection

This document and public_summary.py/test_public.py were added AFTER the frozen
five-file numerical execution. They are not claimed as executed numerical
source. The five source files archived before small01 remain byte-unchanged.
No numerical rerun was used to create the safety projection.

## Actual bounded result

All 11 preregistered cases completed. Original live PV32 versus actual-bank loan:
- M1: external reads 18432 -> 8192 B; KV 12288 -> 2048 B.
- M2: external reads 49152 -> 16384 B; KV 36864 -> 4096 B.
- Output bits and all ten observed intermediate payload/coverage/frequency
  fields matched bytewise. The independently stalled M2 run also matched.
- Normal Matrix issues remained 144 and 432; actual FMA calls remained 73728
  and 221184. Original Scalar primitive counts were identical.
- M1 banked: 32 fills, 160 hits, 192 consume ACKs, 320 bank reads, 64 bank writes.
- M2 banked: 64 fills, 512 hits, 576 consume ACKs, 1024 bank reads, 128 bank writes.
- Both ordinary and stalled local responses retained minimum edge latency.
- Six injected fault cases completed Protocol terminal after controlled drain:
  local fill, external read, external write, accepted Matrix work, an actual
  duplicate physical-bank write, and mutation of published producer bytes.
- Nine loans released after terminal consume. 312 direct foreign admission or
  bank-access attempts were rejected without adding a physical bank edge.

These measurements are software transactions, arithmetic calls and model
edges, not hardware-cycle or speedup estimates. The cache may add model edges
while removing external bytes. The new two-bank physical route is not RTL.
Actual shared A payload identity and unique owner begin_cycle were checked.

## Sticky reset after faults

All six fault cases leave the original Matrix service reset_required=True.
A-lease release and restored Dense job_ready establish only restoration of the
A admission gate. They do NOT permit immediate next work on the poisoned shared
Matrix backend. The next Attention arm rejects this state; any future public
host integration must preserve its original global reset gate and coordinated
backend-reset procedure. This batch does not clear or bypass that requirement.

## Coverage and publication

The actual producer is the original KvAppend owner on synthetic M1/M2 inputs,
with accepted data, exact write ACKs, owner terminal and test-Bus publication.
Original public21 checkpoint/host execution, M128 prefill, fullblock, RTL and CI
were not executed. Existing M128 numerical gate failures are unaffected.

The local receipt contains detailed identities, compiler/native records and
observations. None is public payload. Only the strictly validated projection
may be shared as aggregate results. It accepts closed enum strings and native
non-bool bounded integer counts; it validates case completeness, exact expected
arithmetic/byte counts, count relations, booleans and sticky reset state. Private
source/runtime hashes, arrays, addresses, tags and paths are not copied.

    python -m unittest candidates.qwen2_attention_shared_a_integration.test_cold candidates.qwen2_attention_shared_a_integration.test_public
    python -O -m unittest candidates.qwen2_attention_shared_a_integration.test_cold candidates.qwen2_attention_shared_a_integration.test_public
    python -m candidates.qwen2_attention_shared_a_integration.public_summary --input PRIVATE_RESULT --out FRESH_SAFE_OUTPUT

Eighteen cold/schema tests pass normally and with -O. Tests include every
scalar replaced by a private-path marker, nested/string/nonfinite/bool values,
out-of-range counts, missing/reordered cases and broken counting relations.
