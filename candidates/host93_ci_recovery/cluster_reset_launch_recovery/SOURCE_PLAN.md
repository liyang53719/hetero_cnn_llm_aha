# Narrow source plan

Parent commit da85b638024da3717a30b6da6140f8674f89250c. TEMP_SOURCE; whole-source review GO; actual NOT_EXECUTED.

1. Add host-cluster-reset-launch as a37-stage mode. Reuse FIFO preflight, exact historical FIR gate, selected319 double-split FIFO, current cluster configuration and same-job tools/output directories. Do not change inputs, arithmetic, cases, warnings or the original stimulus.
2. Separate the execution input variant from generation-only stopping: run gains cluster_boundary=False. Old stop_after_generation=True still means the current generation-only variant. The new mode uses cluster_boundary=True and continues all three execution phases.
3. Collect the existing generation census once, directly after generation. Require complete/AVAILABLE zero-header/no-omission evidence, finite18-input/2-output cluster wrapper with6DPI imports, one combo import/callsite, two combinational blocks, and a single matching make-library rule. Preserve unknown root-header syntax/handle counts.
4. Before compilation, verify current generated argument/wrapper/make identities, the fixed parameterized child family and exactly one ENABLE_ACCUMULATOR_SEED=1 override, initialized constructor, Host83 ports and protected symbols. Before runtime, require current child/top archives and new ELF. Preserve all input/generated-source/ELF stability checks.
5. Run the unchanged make argv and unchanged short stimulus under original phase budgets, all charged to the shared job deadline. No launch after compile failure. No later eval or explicit final after the first launch handshake.
6. Strict evidence binds any compile/runtime row to the35 clean preconditions and positive cluster census. Full new-mode completion needs all37 clean rows and the new host ELF identity. Only then can existing cpp_generated/cpp_compiled/reset_launch flags become true; numeric and weights flags remain false. New fixed parent labels identify finite cluster witness failures without raw paths or exception text.

Execution belongs to the sole publisher after source/content review. This worker performs pure Python/static/mock tests only. Original native artifacts are not reconstructed or reused across CI jobs.

Parameter basis: retained13 cluster declares unsigned bit ENABLE_ACCUMULATOR_SEED=0; historical-hash Host SV supplies1 through the pinned endpoint and array. Fixed V3Number/V3HierBlock formatting gives decoded1'h1. Fixed V3Param naming uses the SHA512 longname digest prefix; missing/zero/unknown parameters, arbitrary suffixes and inconsistent child links are rejected. The actual private args remain unavailable and the prior census UNKNOWN remains unchanged.

Coverage note: the execution name predicate checks official digest prefixes of length1..127; the unchanged census suffix limit remains96 characters, so end-to-end acceptance is conservatively narrower. No parser limit is expanded.

Independent SOURCE GO: review_cluster_reset_launch_source_20261019T0932; MANIFEST 1158 B / d5f9c6e56c727a4f15595eb116cfe6f2a2a63dd8d53f413d60de3ece9592ecdd; SUMMARY 5655 B / d0550433add06abb32f26a09b176f94c5f9b54d56b71d182c282fb394ce4f686. Verdict SOURCE_GO_CLUSTER_HOST_COMPILE_RESET_LAUNCH_ONLY. Actual remains NOT_EXECUTED.
