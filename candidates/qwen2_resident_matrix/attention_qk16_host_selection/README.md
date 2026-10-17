# Default-off original Host QK16/BF16 selection

Source-only candidate for hetero_cnn_llm_aha, based on published cc7a893574a79aaf00174723e9141bc367076ed9. This adds constructor selection through the existing HostBlockCollection → HostBlockTop → QwenOwnerKernel → Qwen2ContinuousBlock chain. It is a QK-only partial numeric policy, not the full official-BF16 policy or complete packed Attention implementation.

## Exact source base and installation

Use the exact composed QK16 source closure (83 Scala sources), not the raw repository kernel. Its QwenOwnerProtocol already contains enablePackedQk16Keys and the packed group/step/result/done/abort/stepsDrained wiring. pins.json identifies the 2 edited inputs and 80 unchanged sources; compile_pins.json identifies the original core, 87 dependency jars and Java binary/release. The independently prepared BF16 fragment core is pinned separately. No binary, machine path, existing workspace name, downloaded dependency or generated RTL is part of this package.

The delivery INSTALL_MAP.json is add-only under candidates/qwen2_resident_matrix/attention_qk16_host_selection. Do not replace runtime/main files or patch a frozen or active build. This recipe writes a fresh 3-file overlay, retaining the BF16 core byte-identically and changing only original owner/top constructor declarations, guards and named forwarding. Existing paths and symlinks are refused. Every input is checked before creating output. selection.patch applies with patch --batch --fuzz=0 -p1 to the same exact composed base; prefer prepare.py for pin checking.

Portable replay with explicit caller-supplied paths:

```sh
CAND=/path/to/checkout/candidates/qwen2_resident_matrix/attention_qk16_host_selection
BASE=/path/to/exact-composed-qk16-83-source-closure
BF16=/path/to/materialized-qk-only-fragment-overlay
OUT=/path/to/new-selection-overlay
python -B "$CAND/prepare.py" --source-root "$BASE" --fragment-root "$BF16" --output "$OUT"
python -B "$CAND/test_candidate.py" --source-root "$BASE" --fragment-root "$BF16" -v
```

BASE must already have been composed by the published QK16 owner route and original full-project class-compile recipe; the manifests here give the exact portable relative filenames/content identities. BF16 is generated with the published attention_qk16_bf16_materialize/prepare.py against that base. A raw checkout alone is intentionally rejected, preventing the loss of packed kernel mux wiring.

## Selection and compatibility

For an eventual separately authorized elaboration, construct the original top:

```scala
new HostBlockTop(
  QwenBlockShape(maxTokens=128,retainedMatrix=true,matrixColumns=256),
  weightReadBeats=16,pipelined=true,
  enablePackedQk16Keys=true,enablePackedQk16OfficialBf16=true)
```

HostBlockCollection exposes the same trailing flags. No replacement engine, top, emitter, CLI switch, command ABI, job field or physical port is added. Existing emitters are byte-identical and continue selecting false. Named flags skip the existing kernel H2048 borrower argument without shifting it.

The new BF16 flag requires explicit packed QK16 selection and the original Qwen2 H1536/F8960/12 query heads/2 KV heads/headDim128, non-native profile, retained 256-column Matrix, pipelined owner and 1≤maxTokens≤128. Core ownerDriven/externalMatrix and original packed exclusivity guards remain. With new BF16=false, the existing packed route still admits its prior legal non8960 FFN shapes; this patch does not tighten that contract. Both flags default false. Separate Qwen3.5 M1 restrictions and all old profile guards remain untouched.

## What is preserved

Original owner code from Matrix service construction to EOF is byte-identical, including packed client selection, Matrix drain status, group/step handshake, held result and done, abort, owner mode arbitration and poison. Host command fusion, memory arbiter, DMA, final write fence and result accounting are unchanged. Inverse-edit tests recover the exact original files. There are no new Reg/Mem/IO/Module instances or changed resource geometry in this selection patch. The pre-existing selected QK16 candidate has its own resource cost; a default-off source check is not gate-level identity or area proof.

## Tests and bounded class compile

Eleven source-contract regressions cover exact output/inverse, original fragment, default arguments and forwarding, packed transport tail, non-pipelined owner, unchanged emitters, exact Boolean guard-text projection including illegal combinations and old packed compatibility, overwrite/symlink/drift rejection, and zero-fuzz patch replay. Guard tests interpret exact Scala Boolean source expressions with syntax-only translation; they do not execute Chisel constructors. No simulated handshake or numerical acceptance follows from them.

After independent review and explicit authorization, one copied-closure class compile may be run:

```sh
/usr/bin/timeout --signal=TERM --kill-after=10s 100s python -B "$CAND/compile_only.py" \
  --source-root "$BASE" --fragment-root "$BF16" \
  --cache /path/to/pinned-jar-cache --java /path/to/pinned-java/bin/java \
  --cleanup-helper /path/to/checkout/candidates/qwen2_resident_matrix/portable_owned_cleanup/strict_cleanup.py \
  --output /path/to/new-class-compile-attempt
```

The script makes a private copy, verifies exact 83-source composition and 87 jars plus Java before/after, compiles with 1 GiB heap and one active processor, and limits compiler waiting to 80 seconds. It never invokes an emitter or top entrypoint. receipt.json includes source/class hashes and flags separating class compile from elaboration/RTL/numerical/protocol verification. The pinned existing strict cleanup helper retains the exact direct leader until bounded scans establish original group/observed-identity disappearance, then reaps it; its proof scope is ANCHORED_ORIGINAL_GROUP_AND_OBSERVED_IDENTITIES_ONLY. It does not claim unobserved-tree confinement. TERM/INT/alarm and BaseException routes use that same original-stop cleanup, with spawn/registration protected from signal interruption. Zero/nonzero/TERM control cases are checked separately by test_owned_compile.py. External timeout bounds the overall command; if it fires before a receipt is written, do not claim success. No automatic retry.

## Remaining gaps

This selects only the two QK BF16 materialization hooks. Full-block official policy, PV input/output policy, finite/nonfinite and Scalar underflow equivalence, actual backpressure/abort/poison retirement, scratch bank ownership and ACK/release wiring, six-head scheduling, 384-byte panel and V staging, packed PV6 supply, and joined Host completion fence behavior require their own review/tests. The original Host fence is preserved, but this new combination has not executed its hardware path. Existing Python packed M128 model evidence is a different implementation; it does not establish this top's RTL/full numerical acceptance. No EDA, timing, area, utilization or full29-gate claim is made.

## Recorded result

The single authorized class compile passed: exit 0, 83 sources, 474 classes, 29.47 seconds, input/dependency/Java postflight passed, strict scoped cleanup proof validated, external timeout wrapper exit 0. Eleven source regressions and zero/nonzero/TERM compiler-control fixtures passed before compilation. Independent review additionally exercised a short work-deadline failure. See evidence.json; no RTL, elaboration, hardware protocol simulation or full-block numerical launch occurred.
