# Local Agent handoff: operator RTL generation, simulation and 800 MHz DC

## 1. Accepted input gate

The local Agent must start from the latest remote `main` and treat these files as authoritative:

```text
chisel/three_model_operator_primitives/
config/model_operator_inventory_v3_complete.json
config/clock_policy_800mhz.json
configs/arch_v1.yaml
dc/common_clock_800mhz.tcl
plans/three_model_operator_coverage_v3_800mhz.yaml
```

The accepted source gate is:

```text
PASS_COMPLETE_THREE_MODEL_CHISEL_OPERATOR_PRIMITIVE_SOURCE_GATE
18 independent roots
Qwen2-1.5B             30/30 inventory entries
Qwen3.5-35B-A3B        93/93 inventory entries
Qwen3.8-Flash-Next    150/150 inventory entries
800 MHz / 1.250 ns active clock
```

This handoff does not accept a directory listing, successful elaboration alone or opcode acceptance as RTL functional closure.

## 2. Repository policy

Use only `main`:

```bash
git checkout main
git pull --ff-only origin main
test "$(git branch --show-current)" = main
test -z "$(git status --porcelain)"
```

Do not create a branch. Do not force-push. Do not run `git clean`, remove the sandbox workspace, delete tool caches or delete intermediate logs. New work and temporary evidence must remain available until the final remote SHA is verified.

Record before starting:

```bash
git rev-parse HEAD
java -version
verilator --version
sbt --version || true
dc_shell -version || true
```

## 3. Re-run the portable source gate

```bash
chmod +x scripts/run_three_model_operator_primitives.sh
./scripts/run_three_model_operator_primitives.sh
```

Acceptance:

- Python coverage tests: zero failures;
- Scala/Chisel compile: zero errors;
- ChiselTest: all 18 roots pass deterministic backpressure tests;
- pure-Scala semantic checks pass;
- CIRCT smoke emission produces exactly 18 root `.sv` files;
- `SOURCE_GATE.txt` contains `PASS_CHISEL_OPERATOR_SOURCE_GATE`;
- source audit reports 30/93/150 operator entries and no missing binding;
- active target is 800 MHz and no active 1.0 ns constraint is detected.

## 4. Generate authoritative RTL

The smoke output under `work/generated` is not the committed RTL baseline. Regenerate into a versioned repository path:

```bash
mkdir -p generated/operator_primitives_v3
cd chisel/three_model_operator_primitives
java -Xmx4g -jar ../../work/toolchain/sbt-launch-1.10.2.jar \
  "runMain heteronpu.operator.EmitOperatorPrimitives ../../generated/operator_primitives_v3"
cd ../..
```

Generate or bind every required leaf endpoint. The intended ownership is:

| Leaf class | Required implementation owner |
|---|---|
| GEMM/GEMV/outer/QK/PV | Revision8B-B BF16 Matrix and retained INT8/quantized Matrix paths |
| Vector add/sub/mul/FMA/mask/broadcast | fixed SFU/vector endpoint |
| RMSNorm/group RMSNorm/LayerNorm/L2Norm | fixed norm SFU |
| RoPE/exp2/reciprocal/rsqrt/softplus/sigmoid/SiLU/GELU/signed-sqrt | fixed nonlinear SFU |
| Online softmax | Block32/Block128 online Attention SFU |
| KV append/gather | KV/Sequence Memory endpoint |
| Stable Top-K/stable sort | selection engine; reuse the existing V2 Chisel stable-selection sources |
| Sparse gather-run coalescing | selection + iDMA planner; reuse the existing V2 coalescer source |
| N-gram hash | PLE control/memory primitive; reuse the existing V2 Chisel hash source |
| Depthwise causal/dilated convolution | AHA/state sidecar or dedicated state primitive |
| Bilinear position/spatial merge | vision address/layout primitives |
| State read/write/commit/resolve | Sequence Memory transaction manager |
| MTP compare/rollback | MTP verification and state-action primitives |
| Embedding lookup/multimodal scatter | memory/layout endpoint |

Existing V2 reuse candidates are expected under `integration/gemmini`. Confirm exact emitter object names from source rather than guessing:

```bash
grep -R "object Emit" -n integration/gemmini chisel | sort
```

A leaf may be implemented by existing handwritten RTL rather than re-emitted Chisel, but the binding must be explicit in a machine-readable manifest.

Create:

```text
generated/operator_primitives_v3/MANIFEST.txt
generated/operator_primitives_v3/OPERATOR_COVERAGE.csv
reports/execution/OPERATOR_RTL_GENERATION_V3.json
```

`OPERATOR_RTL_GENERATION_V3.json` acceptance fields:

```text
source_git_sha
java_version
sbt_version
chisel_version
circt_version
root_sv_count = 18
leaf_module_count
module_name_collisions = 0
unresolved_leaf_bindings = 0
sha256 for every emitted or bound RTL file
```

## 5. RTL protocol simulation

Instantiate each root with a leaf-command responder. Randomize independently:

- `launch.valid/ready`;
- `microOp.valid/ready`;
- `completion.valid/ready`;
- `result.valid/ready`.

For every root:

- at least 20 random seeds;
- at least 100 successful transactions per seed set;
- hold output bits stable while ready is low;
- no phase loss, duplication or reorder;
- completion tag mismatch returns `0xe1`;
- completion phase mismatch returns `0xe2`;
- nonzero leaf status propagates without issuing a later phase;
- watchdog, X/Z and protocol errors are zero in positive tests.

Compare every issued phase against the root phase manifest. A delayed completion echo stub is insufficient because it does not prove leaf ownership or payload flow.

Output:

```text
reports/execution/OPERATOR_RTL_PROTOCOL_SIM_V3.json
```

## 6. Leaf numerical RTL simulation

Retain existing numerical anchors for BF16 FMA/Matrix, RMSNorm, RoPE, online softmax, SiLU, Qwen2 KV and attention. Add immutable vectors for the newly required semantics.

### Qwen2

Validate all 30 inventory entries through their bound leaf endpoints. The complete block must include all seven dense projections, Q/K/V bias, independent Q/K RoPE, GQA QK/PV, online softmax and SwiGLU.

### Qwen3.5-35B-A3B

Required new numerical anchors:

- GDN Q/K L2 normalization and query scaling;
- `exp(-exp(A_log) * softplus(a + dt_bias))` decay;
- beta sigmoid;
- state decay, `S^T*k`, delta, rank-1 update and `S^T*q`;
- SiLU-gated GDN output;
- dense-attention Q/K RMSNorm and partial interleaved MRoPE;
- sigmoid attention-output gate;
- stable Top-8 routed MoE plus shared-expert gate;
- MTP accepted prefix and rollback;
- vision patch/block/merge/injection.

### Qwen3.8-Flash-Next

Required new numerical anchors:

- complete low-rank hyper read gate and independent write/inject gate;
- descriptor-selected GDN output gate;
- EOS-aware PLE token history and n-gram hash;
- PLE sparse row fetch, signed-sqrt gate and dilated causal convolution;
- QSA compressed block average/L2 norm;
- non-negative index score clamp and head reduction;
- stable Top-512 with deterministic tie rule: lower original index wins;
- selected-index sort and gather-run coalescing;
- sparse KV gather and sparse online attention;
- Top-10 MoE;
- final hyper merge;
- vision and MTP paths.

For each vector set, bind model revision, source file SHA-256, tensor shape, dtype, tolerance/bit-exact policy and random seed. Do not inject reference output tensors after start.

Output:

```text
reports/execution/OPERATOR_LEAF_NUMERICAL_RTL_V3.json
```

Acceptance:

```text
Qwen2 operator binding coverage       30/30
Qwen3.5 operator binding coverage     93/93
Qwen3.8 operator binding coverage    150/150
missing bindings                          0
CPU/reference tensor fallback             0
```

## 7. Model-family canaries

After per-root closure, run these integration canaries before attempting full models:

1. Qwen2: one complete decoder block plus final norm and LM head.
2. Qwen3.5: three GDN blocks, one dense-attention block, one MoE block and one MTP transaction.
3. Qwen3.8: one GDN block, one QSA block, PLE, Attention and MoE hyper read/write, Top-10 MoE, final hyper merge and MTP.
4. Vision: one patch projection, one vision transformer block, one patch merge and multimodal token injection.

Each canary must show descriptor reads, L2 reads/writes and at least one real stall in every active owner. Completion-only or host-file transport does not pass.

## 8. DC synthesis at 800 MHz

All new synthesis and STA runs must source:

```tcl
source dc/common_clock_800mhz.tcl
hetero_apply_primary_clock clk_i hetero_clk
```

Required clock evidence:

```text
clock name       hetero_clk
period           1.250 ns
frequency        800 MHz
setup uncertainty 0.080 ns
active 1.0 ns clocks 0
```

Run per-root synthesis first, then the combined shell. Preserve hierarchy around the 18 roots and expensive leaves so area and critical-path attribution remains meaningful.

For each run archive:

- analyzed/elaborated source list;
- unresolved reference report;
- clock report;
- constraint report;
- timing summary and all violating paths;
- area/resource/reference reports;
- inferred latch and combinational-loop checks;
- tool version, library, corner, voltage, temperature and wire-load/RC assumptions;
- command log and report SHA-256.

Minimum source-level DC gate:

```text
analyze/elaborate/link errors    0
unresolved references            0
inferred latches                 0
combinational loops              0
requested period              1.250 ns
setup WNS                      >=0.000 ns
hold violations                  0
```

If SRAM timing views are unavailable, black-box them explicitly and label timing/area as logic-only. Do not report a logic-only result as full-chip signoff.

## 9. Performance interpretation after frequency reduction

At 800 MHz:

```text
BF16 512 MAC/cycle        409.6 GMAC/s = 819.2 GFLOP/s
INT8 2048 MAC/cycle       1.6384 TMAC/s = 3.2768 TOPS
W4A8 4096 candidate       3.2768 TMAC/s = 6.5536 TOPS
```

Qwen2 q1024 BF16 at 300 token/s now requires approximately 99.207% wall MAC utilization. Do not use the old 1 GHz utilization result. Operator coverage can pass even if this performance point later fails.

## 10. Commit and push

Commit generated RTL, binding manifest, RTL tests and reports directly to `main`:

```bash
git add generated/operator_primitives_v3 \
        reports/execution/OPERATOR_RTL_GENERATION_V3.json \
        reports/execution/OPERATOR_RTL_PROTOCOL_SIM_V3.json \
        reports/execution/OPERATOR_LEAF_NUMERICAL_RTL_V3.json \
        dc

git diff --cached --check
git commit -m "rtl: generate and verify three-model operator primitives at 800MHz"
git pull --rebase origin main
# rerun all accepted gates after rebase
git push origin main
local_sha=$(git rev-parse HEAD)
remote_sha=$(git ls-remote origin refs/heads/main | cut -f1)
test "$local_sha" = "$remote_sha"
```

Final report must contain both SHA values and state `remote_sha_equals_local_sha: true`.
