# L2 descriptor-v2 multi-op production pipeline

Result: PASS for the frozen retained-Rocket cases.

The production Matrix path is now snapshot -> semantic decode -> algorithmic
Gemmini emitter -> CUSTOM_3 program adapter. It emits programs from resolved
shape/stride/policy fields; generated memh files are test oracles only and are
not instantiated as RTL ROMs.

Randomized-ready pipeline evidence matches all 65 expected operations exactly:
multi-tile OS 36, LOOP_WS 11, Conv identity 9 and Conv 0.5 requant+ReLU 9.
Three pre-issue failures (zero subarray mask, missing bias record and quant
scale fetch error) produce one illegal envelope and zero legal CUSTOM_3 issue.
The shell-level production top runs LOOP_WS through 11 CUSTOM_3 accepts,
retained busy assert/clear semantics and completion event in 99 cycles.

The pinned Gemmini activation encoding defines value 2 as LayerNorm, not
ReLU6. Therefore schema-v2 architectural ReLU6 is explicitly rejected by the
Matrix emitter and must be lowered to the SFU path; it is never mislabeled as
a fused Gemmini operation.

Python 59 PASS, open-RTL PASS, integrated RTL/model PASS, macro-boundary audit
PASS, and production pipeline/emitter Verilator `-Wall` lint are clean.
Evidence: `work/results/l2_descriptor_v2_pipeline/`.

Remaining before L2 closure: explicit 1x1 Conv and no-bias WS vectors/tests,
ReLU6-to-SFU compiler test, then final transitive retained-Rocket/write/event
audit and upstream-clean proof.
