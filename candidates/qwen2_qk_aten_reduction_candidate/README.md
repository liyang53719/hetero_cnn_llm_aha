# Complete Q/K 8-by-8 arithmetic control

This independent software candidate is a numerical control, not the main
hardware architecture. It does not modify the current DUT, Chisel, existing
source closures, historical expectations, or numerical gates. The separate
fixed-4096-MAC resource screen remains a performance NO-GO; bit-exact arithmetic
here does not make that mapping acceptable.

## Actual data path

The candidate first computes RMS from fixed raw input and gamma using the
previously reviewed independent RMS graph. It then computes every Q and K
projection output, with 64 FP32 partials per output. Input depth is processed as
24 groups of 64: eight registers by eight lanes. Register reductions use
offsets 4, 2, 1, followed by lane reductions at offsets 4, 2, 1 and the explicit
zero-tail add. The implementation processes at most 64 outputs at a time, so
the software partial workspace is 4,096 FP32 words, or 16 KiB. Q and K are
serialized. This is not a claim that those partials map to current hardware
ports, contexts or routes, nor a hardware utilization claim. Distinct N outputs
are never reduced together.

Completed raw projections are fed to the unchanged OfficialPrefixOwner Bias
and RoPE jobs through the existing test harness's memory responses and matching
write acknowledgements. All four complete jobs have terminal results, exact
write ACKs and finite published output. No official intermediate is a candidate
operand. The official prefix is executed only after candidate Q/K have finished.

Candidate Q/K then feed the unchanged native causal QK operations and original
owner scalar fold. The complete causal scores are compared with original
upstream BF16 matmul/division AST. Probabilities use the original finite BF16
mask and original softmax AST for the reference; current scalar softmax uses
unchanged original owner statements and ScalarService. Its coverage is sixteen
selected real rows including the prior worst probability row and all current
score-mismatch rows, totaling 1,796 positions. Future current-score cells have
no observations and use an explicit diagnostic zero fill before masking; they
are never included in numerical metrics or treated as DUT computation.

## Observed result

- Complete n0, QR, KR, Q and K have zero uint32 bit differences versus the fixed
  original upstream reference.
- All 99,072 causal score positions have zero uint32 bit differences.
- Current scalar probabilities on the selected rows pass the unchanged gate:
  max error approximately 1.80556e-35; mean approximately 8.35563e-37. There are
  101 tiny bit differences. This is bounded softmax coverage, not a full
  probability acceptance claim.
- Applying official softmax to all candidate causal scores produces zero
  causal probability bit differences versus official scores.
- The projection executed 352,321,536 FMA and 14,680,064 reduction adds. Original
  causal QK executed 405,798,912 native FMA. Bias and RoPE retain their original
  separate scalar operations and are not hidden in those projection counters.

These results establish the tested arithmetic graph's usefulness as a control.
They do not establish a resource-efficient hardware implementation, general
input coverage, complete full-block acceptance, or CI platform identity.

## Bounds and identity

Before full execution, a real one-row K projection and complete original suffix
pilot checks cost, plus a Q first-row extension check against the earlier exact
eight-column candidate. The run is bounded by CPU 120 seconds, address space
4 GiB, total output 64 MiB, and an external 150-second wall timeout. The observed
run used about 9.6 CPU seconds, 9.7 wall seconds, 351 MiB peak RSS and under
4 MiB output. No checkpoint download, CI run, full block or RTL is executed.

Six native runtime identities, raw input hashes, earlier source pins and the
explicit tracked execution-source closure are checked. Runtime is ATen AVX2, MKLDNN disabled,
four intra-op threads, one inter-op thread and deterministic algorithms. This
is a pinned local profile, not a claim of identical CI platform identity.

All real data, detailed reports, native artifacts and receipts remain in ignored
local work. Do not publish or upload them. Only the independently validated SAFE_PUBLIC_V2.json is projected
for aggregate reporting: fixed enums and max/mean/count fields, without tensor
values, coordinates, hashes, shapes or paths. The earlier private diagnostic
SAFE_SUMMARY.json retains static gate metadata and is not the publication
allowlist. Neither summary is a full-block acceptance receipt.

Cold checks:

```
python -m unittest candidates.qwen2_qk_aten_reduction_candidate.test_cold candidates.qwen2_qk_aten_reduction_candidate.test_public candidates.qwen2_qk_aten_reduction_candidate.test_closure -v
```

All commands are cold by default. Real execution requires explicit authorization,
the fixed runtime environment and a fresh fixed output identity. Rerunning into
an existing output fails closed. Further few-partial alternatives must be
reviewed against real resource constraints and a predeclared multi-input test
plan; this successful control is not authorization to copy the CPU graph into
hardware.

## Post-run publication/source repair

The recorded numerical result was produced by the original local01 source
snapshot. It remains unchanged and is not retroactively attributed to this
repaired entry point. The old eight-source freeze and the original executed
versions of changed files are preserved in private repair provenance.

The new entry point has not been numerically rerun. It uses a separate local02
output namespace and a reviewed, explicit closure of 39 tracked source
dependencies, including recursive repository Python imports, original source
 guards, native arithmetic includes, runtime pins and original gate policy.
This is a tracked repository code/evidence closure, not a complete operating-system or DSO closure.
Framework Python source and compiler identities are checked in addition to the
six native files at execution time. It no longer reads the failed historical
attempt's unrelated source inventory or the old diagnostic result to choose
rows. Its sixteen selected probability rows are now an explicit static test
plan matching the prior coverage. Cold tests mask all local work and unrelated
untracked recovery sources and still pass the complete source check.

The strict publication projection rejects unexpected metric keys, strings,
containers, booleans-as-numbers, nonfinite/negative values, impossible counts,
invalid mean/max relations, nonboolean verdicts, and incorrect fixed aggregate
counts. Its independent V2 projection of the unchanged result matches the old
aggregate values byte for byte; this repair does not rerun numerical work.

Actual execution still requires the explicitly fixed recovered raw inputs,
installed runtime, and verified original native arithmetic library. A source
checkout alone does not contain those private prerequisites.
