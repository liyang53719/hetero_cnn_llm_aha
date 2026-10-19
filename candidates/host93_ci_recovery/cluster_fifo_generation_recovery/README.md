# Cluster-boundary / FIFO generation diagnostic

This optional successor is selected only by the existing `host-generation-diagnostic` mode. The coordinator retains its 32 stages and stops after C++ source generation. Default full Host and build-diagnostic behavior remain unchanged. Warning-fatal remains enabled.

Two exact input changes: the reviewed single FIFO valid_o combinational-process split, and one hierarchy selector moved from the endpoint to its existing `bf16_context_lane_cluster16_rev8b_b_candidate` module. Arithmetic, allReady reduction, atomic handshake gates, and the emitted Host SV bytes remain unchanged. Two existing WIDTHEXPAND directives follow their identical source statements from lines 81/100 to 88/107; there are no new waivers.

Source inspection found both cluster outputs read registered FIFO heads with registered read pointers, without current-input, write-through or pop bypass. All 40 current-input/output pairs and 4096 result-word paths were checked. The genuine out_ready → completion_fire → same-context → step_ready dependency remains transparent. Seed-bank state and result/flags read-pointer state remain inside the protected cluster; only handshake/admission control is exposed. This finite source argument is not an actual SCC or behavioral-equivalence result.

Official fixed 5.053 source supports one specialization/library rule for equal parameters across the 256 instances. Each created wrapper gets its own model and sequence-number storage; it does not create an independent VerilatedContext. The wrapper has one syntactic combo_update call site, without a demonstrated dynamic calls-per-cycle bound. Sequence update responds to any classified clock change, not only a rising edge. Generation may observe an archive build rule, not a compiled archive.

The new bounded report observes candidate count, finite wrapper ABI counts, top reference, makegraph archive rules, and mapped handles from generated files. Missing files remain MISSING; unsupported encodings remain UNRECOGNIZED. The source expectation of 256 never supplies an actual count. No generated code or full native log is published.

The v1 SOURCE review identified four census-only structural-consumption gaps. This v2 binds handles to a closed target class, permits only the fixed make/header guards, rechecks candidate membership, and requires coherent finite-wrapper counters. Unsupported syntax remains unknown.

SOURCE independently reviewed. Actual generation NOT_EXECUTED.

## v3 finite boundary closure

v2 remains retained as SOURCE HOLD. Only C01-NESTED and C04-PRODUCER change: handles must be direct members of the closed target root class; nested class/struct/union and other nested candidate declarations remain unknown. No nested type or preprocessor evaluation is attempted. A wrapper with zero always_comb blocks now keeps its warning census and reports UNRECOGNIZED_SYNTAX; it cannot produce a contradictory FINITE_PARSE report.

Retained v2 review: review_cluster_fifo_generation_v2_source_20261019T0753; MANIFEST 482289e1666f448ee38f2c0d3560a6e6814b788710b4ee99411aca348ae86b3a; SUMMARY 82d5f380c70248f3793b68d3134837cf4771588dc18546a7588a06c8a7af41b0.

Independent SOURCE review: review_cluster_fifo_generation_v3_source_20261019T0759; MANIFEST 2198 bytes / ae4cb32c220aa1b8e20dd2a83fa68a43048b8aa20176b93aa4e2e4016bc32f8e; SUMMARY 6919 bytes / 791bb998b85747a22dd018c37881d8f47af600c98851ed5e921cfe0702c692c4. Verdict: SOURCE_GO_CLUSTER_FIFO_GENERATION_DIAGNOSTIC_ONLY. Actual remains NOT_EXECUTED.
