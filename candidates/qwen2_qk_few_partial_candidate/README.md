# Fixed P2/P4 arithmetic screen

This independent, cold-by-default candidate evaluates two preregistered FP32
projection graphs. Each output has P=2 or P=4 positive-zero partials, updated
with FMA(weight[k], activation[k], partial[k%P]) in increasing k. Partial values
persist across refill and 1024/512 boundaries. P2 folds S0+S1; P4 folds
(S0+S2)+(S1+S3). A separate positive-zero addition terminates each graph.
There is no intermediate BF16 rounding. Bias and RoPE use the unchanged actual
owner and its memory/ACK harness. Original native QK and original Scalar owner
statements consume these independently produced outputs.

CONFIG.json preregisters real baseline, one fixed channel-sign seed and one
fixed channel-permutation seed. Every case retains the full official geometry;
the original upstream AST is comparison-only, executed after both candidate
prefixes. All six results, including failures and incomplete cases, are kept.
No result-dependent graph or seed selection is allowed. Four additional
synthetic boundary checks per graph cover signed zero, cancellation, refill
boundaries and bias-before-BF16 rounding. They are not statistical coverage.

One process has a total 120 CPU-second, 4 GiB address-space and 64 MiB output
budget. The launcher must additionally enforce 150 wall seconds. Before the
six-case execution, a full-depth 16-row projection/suffix pilot for both graphs,
a bounded native QK pilot and 2048-position Scalar pilot predict total cost.
Prediction above 95 CPU seconds rejects all six cases. A later 110-second CPU
soft stop records incomplete coverage; it does not grant a numerical PASS.
Full original Scalar probability coverage is required to claim a complete
case. Source/configuration hashes are persisted before compilation and pilot.

Run cold checks with `python -m unittest
candidates.qwen2_qk_few_partial_candidate.test_cold`. Running the probe without
`--execute` only verifies tracked dependencies. Numerical execution additionally
requires the pinned private raw inputs, recovered runtime and original native
library in work; none is published. Six native identities, framework Python
sources, compiler identity and tracked repository dependencies are checked.
The tracked manifest is a code/evidence dependency snapshot, not a complete
system/DSO closure. Local pinned profile does not establish CI platform identity.

The kernel uses a fixed 128-float software partial working set. This is an
arithmetic graph screen, not a Chisel implementation or hardware performance
claim. Current physical lanes retain their output-coordinate meaning. The
conditional P2/P4 context schedule and terminal tree need actual RTL changes;
existing drivers do not implement it. The prior 64-partial control remains a
numerical comparison and retains its hardware performance NO_GO status.

Detailed results, tensor data, positions, tensor hashes, source provenance and
all receipts stay under private work. AGGREGATE.json is an intermediate local
record, not a release artifact. Only a separately validated strict aggregate
projection may be shared. No fullblock, RTL or CI execution is part of this
screen. Original numerical policy remains unchanged.
