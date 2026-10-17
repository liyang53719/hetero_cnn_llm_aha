# Qwen2 M16/M128 replay identity source successor

This source-only successor adds path-free byte identities for the current
same-job M16 prerequisite and M128 assigned-27 run. It retains a fixed inventory
of input, native reference, scalar reference, actual-output and attention
capture identities. No tensor values, payloads, weights, private logs, process
identities or absolute paths are published.

The previous successful numerical run 39012470402 on commit
2e591b6df29fc08504dca264264b149c27e2cf95 remains an assigned-27 result. Its missing
historical per-stage identities cannot be recovered from its seven safe JSON
files. The new emitter has not yet been exercised by a qualified numerical run.

## Retained scope

- Both row counts 16 and 128 have 116 native exports, 22 scalar outputs per role,
  29 sequential exports, thirteen selected checkpoint files and fourteen loaded
  input-provider identities.
- Each completed actual run contributes nineteen sealed output files, a separate
  SiLU file and ten attention fields with raw/presence/frequency files.
- Direct persisted-file hashes, source-defined byte permutations, and authenticated
  snapshot-only provider hashes are distinguished explicitly. Logical IDs are
  path-free. Storage dtype/layout and logical dtype/layout remain separate.
- Causal capture hashes distinguish full storage containing sentinels from the
  observed logical values. M128 scores/logits/prob/softmax_fp32 each observe 99,072
  of 196,608 slots; 97,536 future positions remain unobserved. No expected values fill
  missing actual observations.
- The explicit mask remains unobserved. softmax_fp32 has fixed-scalar causal
  bit-exact coverage but no approved official FP32 tolerance. Full 29, RTL and
  hardware acceptance remain false.

## Authority and failure behavior

The metadata artifact alone grants no readiness or acceptance. Its source-defined
status explicitly requires the successful parent receipt, exact manifest hash,
and final unchanged-deadline check. An artifact written immediately before a
failed deadline check can be uploaded, but its parent readiness stays false.

The existing full numerical receipt is persisted before final identity hashing.
A later metadata failure preserves completed numerical evidence while making
the overall freeze-validation attempt fail. Its safe diagnostic contains only
phase, exception class and a fixed allowlisted code; unknown errors use UNKNOWN.
No exception message is projected.

## Preserved runtime

The six raw-source changes are the parent, parent tests, emitter, emitter tests,
M128 input contract and M128 workflow. The workflow adds one fixed safe artifact
path. The M16 workflow, producer sources, strict cleanup, numerical arithmetic,
terminal validators and all 423 static M128 composition entries remain exact.

Preparation runs after qualified reference cleanup under the original 300-second
reference receipt stop. Finalization runs after full M128 cleanup and terminal
postflight under the original 2430-second receipt stop. M16 remains 900/930 seconds;
M128 remains 2400/2430 seconds; external TERM/KILL remain 4910/4920 seconds. There is
no per-edge instrumentation, numerical recomputation or additional grace.

The standard-library reader uses bounded streaming and rejects aliases, traversal,
size/hash/schema drift and incomplete reads. The static inventory file describes
source-derived geometry and caps; it is not an observed tensor manifest or a
throughput guarantee.

## Cold evidence

SOURCE_COLD.json binds the reviewed source map, complete disposable-copy cold
matrix, isolated loader checks and genuine 424-file source composition. Synthetic
byte and virtual-reader fixtures test metadata and control boundaries; they do
not execute or reproduce a model forward. Independent real-file Reader tests
cover filesystem and deadline failures. The prepare/finalize control fixture
uses explicit byte-projection mocks; the real full-output projection is tested
separately with synthetic M16 bytes.

A future replay-ready result requires one separately authorized fresh combined
M16→M128 freeze-validation run after actual Git closure checks. Publishing the
changed workflow is itself a launch action. This evidence does not authorize it.
