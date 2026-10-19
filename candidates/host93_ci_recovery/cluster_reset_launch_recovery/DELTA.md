# Exact delta

- Changed production sources: run.py and execution/host_execution.py only, with their immediate RUN_PINS/ENTRY and cold-test pins. No change to FIFO/Icarus, original stimulus, Scala, FIR/SV expected hashes, configuration or census/parser source.
- Added mode host-cluster-reset-launch:3 FIFO +34 frontloaded Host stages=37. Existing35/34/16 sequences remain intact. No resource increase.
- Execution interface adds explicit cluster_boundary=False. New cluster witness is separate from the original endpoint/eight-handle witness; the latter remains for its original mode. New code does not read the unknown root header for qualification.
- The new witness binds current generated identities, arguments, constructor, Host83 declarations, archive rules and compiled artifacts. It has fixed CLUSTER_GENERATION_WITNESS labels with seven finite codes. No -Wno-fatal or error suppression is introduced.
- The unchanged short stimulus qualifies real reset release plus one launch edge only; AXI inputs stay zero. Runtime-handle cardinality, complete memory protocol, numeric results and weights remain unqualified.
- Publisher workflow changes only its explanatory comment, step title and selected mode. Other execution text, deadlines, permissions, upload gate, micro/build workflows remain unchanged.

Previous actual review: review_fifo_ready_generation_actual_39226255480_20261019T0913, manifest5391de4dac6d078be67847c4aa341542733784256b329b6815dce1c7c1b7cbb0, summary43c8f1b3d2d1a09f6f07c988e9f5052286f99d145ddb4db96e234f886945c772. It grants only FIFO four-state extraction and Host generation diagnostic scope.

New source review GO; new actual NOT_EXECUTED.

## Parameter-source correction before review

The unreviewed v1 draft mistakenly consulted the older repository-root same-named cluster module and proposed a no-parameter/base-name gate. That draft was never published or executed. The corrected v2 uses the pinned retained13 projected cluster (SHA256 c7fd146302112613515e6fa86af152496cb8d753ef9a425eb0cdbe0252ef073e), which declares unsigned bit ENABLE_ACCUMULATOR_SEED with default zero; the fixed Host SV passes one through endpoint and array to every cluster. The original retained13 table and all RTL bytes are unchanged.

Fixed Verilator revision4e194cc3ec8e27b18e17f80d7f99c15f984bbdae serializes sized unsigned bit1 as 1'h1, then shell-escapes its quote. The new child gate consumes exactly that decoded value, one known parameter and a consistent specialization name throughout args/wrapper/constructor/archive. V3Param derives that name from the SHA512 of the fixed module-plus-parameter longname; only the corresponding hexadecimal digest prefixes are accepted. The prior public census alias and UNKNOWN specialization are not treated as absence of parameters. No private prior args are reconstructed, and any different observed form remains a fixed-code rejection.

Coverage note: the execution name predicate checks official digest prefixes of length1..127; the unchanged census suffix limit remains96 characters, so end-to-end acceptance is conservatively narrower. No parser limit is expanded.

Independent SOURCE GO: review_cluster_reset_launch_source_20261019T0932; MANIFEST 1158 B / d5f9c6e56c727a4f15595eb116cfe6f2a2a63dd8d53f413d60de3ece9592ecdd; SUMMARY 5655 B / d0550433add06abb32f26a09b176f94c5f9b54d56b71d182c282fb394ce4f686. Verdict SOURCE_GO_CLUSTER_HOST_COMPILE_RESET_LAUNCH_ONLY. Actual remains NOT_EXECUTED.
