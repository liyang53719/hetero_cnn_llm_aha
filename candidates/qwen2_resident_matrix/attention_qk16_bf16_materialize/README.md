# Isolated packed QK16 BF16 materialization fragment

This is a source-only, default-off candidate for hetero_cnn_llm_aha. It is not a full official-BF16 block policy, publication, launch configuration, RTL, or hardware equivalence result.

## Portable installation and replay

The delivery-level INSTALL_MAP.json maps each file to its repository-relative destination. No compiled classes, jars, bytecode caches or machine-specific paths are shipped. Dependencies are content-pinned in pins.json; neither an old workspace directory nor an absolute path is required.

Use a checkout containing the published `attention_qk16_owner_route` source recipe and unchanged original helpers. From any working directory, choose explicit absolute or relative paths:

```sh
REPO=/path/to/checkout
BASE=/path/to/new-packed-base
OUT=/path/to/new-bf16-overlay
CAND="$REPO/candidates/qwen2_resident_matrix/attention_qk16_bf16_materialize"
python -B -c 'import sys; from pathlib import Path; sys.path.insert(0,sys.argv[1]); from candidates.qwen2_resident_matrix.attention_qk16_owner_route import prepare; prepare.compose(Path(sys.argv[2]))' "$REPO" "$BASE"
python -B "$CAND/prepare.py" --source-root "$BASE" --helper-root "$REPO" --official-policy "$REPO/candidates/qwen2_resident_matrix/official_bf16/chisel_policy.patch" --output "$OUT"
python -B "$CAND/test_candidate.py" --source-root "$BASE" --helper-root "$REPO" --official-policy "$REPO/candidates/qwen2_resident_matrix/official_bf16/chisel_policy.patch"
```

The base directory must be new for the published source recipe. Our prepare.py accepts only the exact pinned composed Qwen2Block and policy/helpers; it rejects existing output paths including symlinks, validates everything before creating its output, and produces only `chisel/continuous_prefill/src/main/scala/heteronpu/continuous/Qwen2Block.scala`. An existing matching composed source root can be supplied directly instead of running the recipe. The patch artifact applies with `patch --batch --fuzz=0 -p1` to that same exact base; prefer prepare.py because it enforces all pins and refuses overwrite. Never patch an active build.

Opt-in is the trailing constructor Boolean `enablePackedQk16OfficialBf16=true` on `Qwen2ContinuousBlock`; it requires `enablePackedQk16Keys=true`, whose existing owner/external-matrix/Qwen2 geometry guards remain. Existing constructors omit it and stay false. No HostBlockTop/owner-kernel option propagation is supplied: production selection requires a separately reviewed integration. Do not layer this fragment with a full official-policy patch or another QK materialization patch.

## Numerical boundaries

Use existing `F32.bf`, which calls `TensorMath.bf16Rne` and stores the BF16 bits in the upper 16 bits of an FP32 container with the lower 16 bits zero. Rebase the two QK hooks from `official_bf16/chisel_policy.patch`: round only the terminal ordered 16-lane fold before existing scale multiplication; round the scaled score once before both score SRAM write and max comparison. Intermediate fold adds, scale constant, scalar opcode, softmax, PV and all other phases remain unchanged. These two rounds are distinct required materialization boundaries, not duplicate rounding of the same boundary.

A finite FP32 value can round to BF16 infinity. The enabled candidate routes a nonfinite rounded dot or score through existing `packedSelectedFault` before issuing scale or publishing score/commit, respectively. Existing poison/held-result drain logic handles that fault; no new state, storage, register, memory, port, matrix geometry, handshake or counter is introduced. The disabled branch preserves the original arithmetic and transitions. Source preservation is checked, but gate-level identity is not claimed.

## Validation and limitations

The explicit `python -B .../test_candidate.py` invocation above runs eleven source-contract and independent mathematical/reference tests. Nearest-even checks compare the existing helper's integer formula with exact rational midpoint selection for every finite BF16 boundary, both signs, below/at/above ties (195,840 cases), plus explicit sign/carry/subnormal/finite-overflow vectors. Tail key16 and max tie-order tests are reference projections. The source inverse test verifies all changes are limited to the intended constructor and two boundary sites. Tests distinguish a rounded score from a raw score and verify no second installation.

These are not actual hardware simulations. No RTL, Chisel elaboration, EDA, full-block numerical launch, or existing running-job intervention was performed. A Scala compilation, if recorded separately, only establishes source type-checking.

## Unresolved shared-policy dependencies

The full official policy adds `Qwen2NumericPolicy` and an owner-job field, alters RMS/RoPE/PV/SiLU/residual/dense semantics, and touches eight source files. Its shape guard requires maxTokens=1024 and resident public21 routing; packed QK16 currently requires maxTokens<=128. This fragment deliberately does not weaken those guards or claim full-policy composition. The full owner/host/resident policy and PV output materialization still need their own reviewed integration.

BlockScalarFloat legacy Add/Mul rejects inexact underflow, whereas the Python schedule's default vector arithmetic permits it. This candidate does not change scalar exception policy. Thus ordinary finite QK materialization is aligned, but arbitrary exceptional-input equivalence is not established. Existing Chisel BF16 helper canonicalizes NaN; the Python helper preserves its raw nonfinite payload. The candidate refuses nonfinite materialized values and does not use NaN payload equivalence as a correctness claim. Backpressure, abort and poison-drain retirement have not been executed in RTL; the tail/max check is an arithmetic ordering projection only. No timing, area, resource count or numerical full-block acceptance is asserted.

## Class compile result

One bounded copied-83-source closure compile completed with exit 0, 474 classes, elapsed 29.44 seconds, and its process group absent according to killpg(pid, 0) returning ESRCH (not a proof that no detached descendants existed). Original dependency/Java/source preflight passed before and after. See the sanitized `compile_evidence.json`, which records the original receipt hash and class-hash-manifest hash without shipping binaries or machine paths. No executable top or emitter was invoked.
