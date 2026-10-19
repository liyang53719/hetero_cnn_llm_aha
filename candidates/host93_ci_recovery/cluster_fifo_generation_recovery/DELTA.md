# Exact input and observer delta

- FIFO path: deps/common_cells/src/cc_passthrough_stream_fifo.sv. Base 4411 bytes / 68de1c713e40d97950591111dccd37a7546025f7fe6750fa3092826422557352. Derived 4536 bytes / d5482112dccd8a60bb142982fded05b64658b097b4227bf21a514f2da5d34e70. Only the valid_o assignments move to their own combinational process, preserving the procedural flush and pointer predicates.
- Config: sole `hier_block` target becomes the existing cluster. Exactly two existing WIDTHEXPAND directives move 81→88 and 100→107 on identical statements and the exact derived hash. No other warning rule changes.
- Coordinator: append `--fifo-valid-split` and `--cluster-boundary` only for generation-diagnostic. Same stage order, resources and native argv outside those options.
- Execution: explicit derived-closure bool at all five closure checks. Default false retains the original base closure.
- Census: fixed cluster public alias, makegraph/root-header read bounds, observed rule and mapped-handle counts, fixed FIFO source-derivation identity. Retain original endpoint observation support; expose no arbitrary generated suffix/path.
- Pin/test/ENTRY updates follow changed buffers. The enclosing SOURCE manifest is authoritative. Copied historical candidate/component manifests and historical cold-result files are not new evidence. The two refreshed component metadata files preserve their earlier baseline references and separately identify the current variant.

No actual native tool executed during this SOURCE work. Prior FIFO 5180 checks cover extracted combinational logic plus manually controlled state, not FF/reset/delta-cycle equivalence. SOURCE independently reviewed.

## v2 finite review successor

The retained v1 had four census-only gaps: out-of-class/conditional/unterminated handle declarations; make declarations inside unexpanded define or false conditional; candidate-set drift after enumeration; and contradictory finite-wrapper counters. v2 closes only these finite forms, with source-only negatives and known-guard positives. run.py changes only its transitive RUN_PINS identity; extractor/config/execution/resource code stays byte-identical to v1.

Retained v1 SOURCE HOLD: review_cluster_fifo_generation_source_20261019T0744; MANIFEST SHA256 4f73e452bd5ab2ca21530727d31b23ee78d958d31965cc42d7d54271dbacef0d; SUMMARY SHA256 2a9f7aa67285ce853bacd82fd5d0049d385602d8a0a7e411da918d08c831e70a. Only C01–C04 are changed in v2.

## v3 finite boundary closure

v2 remains retained as SOURCE HOLD. Only C01-NESTED and C04-PRODUCER change: handles must be direct members of the closed target root class; nested class/struct/union and other nested candidate declarations remain unknown. No nested type or preprocessor evaluation is attempted. A wrapper with zero always_comb blocks now keeps its warning census and reports UNRECOGNIZED_SYNTAX; it cannot produce a contradictory FINITE_PARSE report.

Retained v2 review: review_cluster_fifo_generation_v2_source_20261019T0753; MANIFEST 482289e1666f448ee38f2c0d3560a6e6814b788710b4ee99411aca348ae86b3a; SUMMARY 82d5f380c70248f3793b68d3134837cf4771588dc18546a7588a06c8a7af41b0.

Independent SOURCE review: review_cluster_fifo_generation_v3_source_20261019T0759; MANIFEST 2198 bytes / ae4cb32c220aa1b8e20dd2a83fa68a43048b8aa20176b93aa4e2e4016bc32f8e; SUMMARY 6919 bytes / 791bb998b85747a22dd018c37881d8f47af600c98851ed5e921cfe0702c692c4. Verdict: SOURCE_GO_CLUSTER_FIFO_GENERATION_DIAGNOSTIC_ONLY. Actual remains NOT_EXECUTED.
