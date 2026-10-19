# Minimal actual-production Host dependency-visibility proposal

## Recommendation

The smallest source-change candidate is to replace the one hierarchy selector in `candidates/host93_ci_recovery/configuration/generate_4vlt.py:329`:

- Current: `hier_block -module "qwen2_matrix_command_endpoint"`
- Candidate: `hier_block -module "bf16_context_lane_cluster16_rev8b_b_candidate"`

Do not retain the endpoint selector alongside the cluster selector. Leave all production RTL, the assembled Host SV, and the complete MatrixPipelineService handshake equations unchanged. This uses an existing datapath module, introduces no model layer, and retains one generated combo_update call per actual protected boundary. It is a proposed relocation, not an implemented, executed, or established fix.

This is the smallest code delta, not a demonstrated smallest runtime-risk choice. It moves the protected instances from eight endpoints to 256 existing clusters, changes the generated internal ABI/scheduler, and requires a new exact hierarchy witness. It must not be presented as production equivalence or as proof that all 32 Host warnings disappear.

## Exact source of the current boundary

`configuration/generate_4vlt.py:315–333` renders the four config files; line 329 is the only selected hierarchy module. `execution/host_execution.py:269–280` supplies these configs to the pinned backend with `--hierarchical`; it does not add -Wno-fatal. The ordinary scripts under `chisel/continuous_prefill/scripts/` and their older multi-boundary .vlt files are not this actual's boundary authority.

The pinned `development_snapshots/canonical_host93_verilator_seqnum_build_source_20261018/DERIVED_V3ProtectLib.cpp:255–264` emits the one combinational call. Lines 454–461 put all non-clock inputs into it; 473–494 put every output into it. Splitting output assignments while retaining that dependency-bearing call does not expose the missing cones.

The actual 39204020851 summary records a 18,165-byte endpoint wrapper, SHA256 `532ce9e8015855a20648576c012c3187ccf4b1feb5c5f1366d00166f60b6efdd`, 22 combo inputs, 21 outputs, one combo_update import/call, and two always_comb blocks at 249/375. Handshake outputs are COMBO_RESULT. The observer still says specialization UNKNOWN and dependency_conclusion NOT_ESTABLISHED. The separately tested transparent/opaque micro pair supports the mechanism but has a different interface and is not production equivalence; its summary remained INCOMPLETE after opaque-observation rejection.

## Why the existing cluster is the useful boundary

All retained citations below refer to the independently hash-verified final postimages pinned by `candidates/host93_ci_recovery/retained13/SOURCE_PLAN.json:expected13`, not unpatched repository base RTL. The assembled MatrixPipeline postimage has SHA256 `83516358916a6bb4a4816d700f056aae028c62dd0cc8891ea97f0cb9fea958cc` and logical repository path `chisel/continuous_prefill/src/main/scala/heteronpu/continuous/MatrixPipeline.scala`.

- `rtl/integration/qwen2_matrix_command_endpoint.sv:28–43` owns command/completion state and exposes its actual equations. Its matrix child at 29–42 contains the seed, output, and step-readiness logic.
- `rtl/matrix/candidates/rev8b_b/bf16_outer_product_context_array_rev8b_b_candidate.sv:56–80` instantiates the front control. Lines 81–100 distribute its control outputs. Lines 105–134 instantiate 32 existing clusters; every cluster uses only `.ENABLE_ACCUMULATOR_SEED(ENABLE_ACCUMULATOR_SEED)` as an explicit parameter override. Lines 119–134 are the proposed cut.
- The cluster's only output ports are `lane_out_o` and `cluster_flags_o` (`bf16_context_lane_cluster16_rev8b_b_candidate.sv:17–18`). Flags come from its registered FIFO (29–39). Lane results are the existing lane result-FIFO reads (`bf16_context_fma_pipeline_lane5_rev8b_b_candidate.sv:53,70–75`). No ready/valid/control output crosses this cut.
- Array line 136 forwards lane_result to acc_o; endpoint line 28 forwards this to out_acc_o. In assembled `MatrixPipeline.scala:162–163`, these values feed values.enq.bits, whose actual storage writes are sequential at lines 16–21. They do not determine the current output FIFO's ready signal. Cluster flags are reduced at array line 104 and connected to endpoint-local mflags at endpoint line 42; mflags is not used in the endpoint handshake equations.

Consequently broad dependencies on the *remaining datapath outputs* do not invent the observed same-cycle handshake return through the cluster boundary in the inspected production cones. Command handshake, seed/retirement handshake, and admission control stay transparent to the parent scheduler; seed-bank state and result/flags read pointers remain inside the cluster.

### Real feedthrough and atomicity must stay

The assembled MatrixPipeline source remains unchanged, notably allCommandReady/allStepReady/allOutValid/allCompletion at 73–76, allBegin/allCommit and their gated leaf valids at 115–130, and cmd/step/out/completion wiring at 147–166. In particular, never remove the AND-of-selected-leaves condition to silence a warning.

The real out_ready → completion_fire → same-context availability → in_ready chain remains in `bf16_context_scheduler5_rev8b_b_candidate.sv:37–42`, with endpoint active gating at endpoint line 28. MatrixResultFifo's same-cycle pop/enqueue readiness (assembled Scala 18–19) and pipe=true tags (54) also remain. Seed admission/hold behavior and all seed state/fault equations remain in front-control lines 87–155, outside the proposed boundary.

Moving only to the outer-product array still hides seed/step/output handshakes together. Moving to front_control or scheduler likewise hides mutually coupled control cones; these are not sufficient repairs. Adding the cluster selector while retaining the endpoint cut also leaves the offending outer abstraction intact.

## 256 instances are not 256 independent builds

The production service instantiates eight endpoints (`MatrixPipeline.scala:65`), and each fixed production array creates 32 clusters (array 55,105). That implies 256 cluster instances, with separate runtime state/handles. The cluster module has only the ENABLE_ACCUMULATOR_SEED parameter (cluster 3–5); all these instances inherit the same enabled setting. The cluster index changes wiring/part-selects, not a cluster parameter. The source therefore describes one parameter specialization reused at 256 instances, not 256 distinct parameter-specialized numerical designs.

The expected build arrangement is one reusable child library for that specialization plus the parent, but the relocation has not been generated. Count actual child argument files, libraries, parameter settings, and runtime handle declarations before claiming the generated build arrangement. Do not equate instance count with build count, and do not forecast build time, memory, simulation speed, or a 32x slowdown. More boundary instances and changed data marshalling are material, unmeasured risks.

If retaining exactly eight numerical datapath boundaries is a hard requirement, the existing array cannot be used unchanged because it contains front control. That alternative needs a real RTL separation of front control from the 32-cluster datapath, with an explicit datapath-only module/interface. It changes retained-source pins and is a larger refactor/new hierarchy layer, not the minimal no-new-layer proposal.

## Minimum production integration scope

1. Change the selector and exact expected config bytes; strengthen `configuration/test_tiny.py:167–175` to assert the target name, not only one hier_block. Refresh `configuration/ENTRY.json`, `COMPONENT_BINDINGS.json`, `RUN_PINS.json`, and their enclosing exact-byte coordinator pins via the established pin-update path. Do not hand-edit an already frozen generated .vlt.
2. Extend the bounded observer for the *specific* new cluster target: `execution/generation_diagnostics.py:33–43,255–287,481` currently only recognizes endpoints and endpoint handshakes. A cluster wrapper cannot honestly inherit the old 22/21 observation or UNKNOWN/AVAILABLE interpretation.
3. Replace the exact endpoint witness, not weaken it. `execution/host_execution.py:294–346` requires endpoint class names, one endpoint specialization, and exactly eight endpoint chandle paths. The new witness must establish the observed enabled cluster specialization, one generated combo_update per wrapper, 256 unique expected instance-state handles, scope mapping, wrapper-before-SV ordering, and initialized sequence state. Reverify the unchanged Host 83-port interface (349–353) and the existing readonly fields against fresh output. Their old internal ABI is not inherited.
4. Retained13, the fixed Host SV, compiler/backend source, numerical implementation, handshake equations, and the other three config contents can remain byte-identical for this candidate. No generator patch to split or duplicate combo_update is needed. Generation-only diagnosis can precede any full compile or runtime authorization.

## Acceptance and stopping conditions

An authorized next trial should use the actual fixed Host/retained13 sources, same backend, warning-fatal unchanged, and existing bounded generation limits. Preserve the all35 baseline census and collect representative new warning paths; a lack of endpoint-named warning headings alone is not success because relocation can rename the nodes.

For this Host candidate, require no remaining Host-side artificial handshake SCC, no new unclassified warning, source/hash identity preservation, exact new child/wrapper/handle witness, and explicit visibility of the real out_ready→step_ready feedthrough. The independent three iDMA warnings can still make the overall generation command nonzero; retain that truthful failure instead of introducing suppression. Do not call a generation-only result functional/protocol/numerical signoff. Subsequent authorized behavioral comparison must cover stalled command/seed/output/completion traffic, simultaneous retirement and same-context issue, clock gating, reset/abort, and eight-leaf atomic transfers.

No repository changes, native toolchain/elaboration/compile/runtime, network fetch, dispatch, or publication were performed in this review. Only this isolated report and input manifest were written. The fixed historical SV and all thirteen retained postimages were rehashed. Full production dependency/behavior verification remains open.
