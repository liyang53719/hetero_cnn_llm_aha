# Separate postterminal reference closure — M16 Attention component only

**PASS for the separately recovered M16 Attention-component numerical comparison; the original production r3 attempt remains `FAILED_RETAINED`.** One new reference-only process exited 0. The DUT was not rerun. Both previously saved real original-observer and identity-observer arms independently match the unchanged recipe: each has **24,576 output words, 1,632 causal score words and all ten field value/presence arrays** equal bit-for-bit. Each frequency contract is valid, but they are deliberately not identical: the DUT normalizer frequency is **1**, while the reference collector frequency is **`8*(token+1)`**. The independent audit checked 351,936 field cells across the two archived arms and the new reference.

This closes only this saved **M16 Attention component**. It does not relabel the old process as successful, supply its missing original `RESULT`, or determine its exact interruption phase. The original M128 CPU FAIL, earlier bf16/fp32 failures, canonical task states and final full-M128 goal remain unchanged. This is not official full-layer/Transformers complete-forward acceptance, a complete block, RTL, hardware cycles, utilization closure, a performance comparison or optimization adoption.

## Preserved blocker and narrow repair

Recovery r1 was **blocked in static review and never run**. Its boundary raised `ValueError` for denied bytecode-cache opens; normal `SourceFileLoader` does not catch that exception to fall back to source. `-B` disables cache writing, not cache reading. Keep the original blocked review and source intact.

The r2 functional repair changes that cache-read rejection to `PermissionError`, still denying cache access while allowing the standard loader's source fallback. The profile/action policy identity and tests are updated, but worker, supervisor, recipe and durable helper remain byte-identical to r1. Two harmless real-loader/audit-hook tests cover a missing cache and an existing valid cache containing a deliberately different synthetic value: the source value is loaded and the existing cache is not changed. The retained source review reports 14 author-suite cases in each normal/optimized mode, plus separate 12-case boundary and 11-case admission suites. These overlapping suites are not aggregated into a unique-case claim. They are historical source-only tests, not reference execution. The original production r2 header-classification failure and production r3 header-only qualification repair are preserved in the preceding [failure package](../qwen2_production_attention_diagnostic/README.md).

## Isolation, phase evidence and its limits

The recovery seals all 89 original artifacts, frozen sources, operand-prefix pins and both real terminal receipts before execution. Preflight necessarily reads archived bytes **for SHA checks** and terminal metadata; it does not decode and return their captured arrays to the oracle. Both saved public3 terminals and the independent saved-pair review are admitted before reference import. After the read guard is installed, old-attempt artifact reads are denied until the recipe returns successfully, even if an integrity flag is requested. Only the fixed `qr`, `kr`, `v` operand prefixes are recipe value inputs.

The pinned AST/scalar reference uses the existing Fraction/integer quotient-remainder RNE and scalar polynomial implementation, with shared exact primitives disclosed. It does not use the archived DUT output as an oracle. It imports no Matrix, production DUT, NumPy, YAML or ctypes/native libm-FMA adapter. CPython, stdlib extension code and pinned system libraries remain runtime dependencies: this is not dependency-free execution. Before-recipe and postflight inventories each qualified 138 modules and ten mapped files.

After `RECIPE_COMPLETE`, reference artifacts are saved and only then are old raw archived arrays decoded for shape/extent, causal presence, frequency/sentinel and exact-value comparisons. This isolation conclusion is based on pinned source/dataflow, completed guards, durable phase order and runtime provenance. **It is not a per-open syscall history or a sandbox against arbitrary malicious Python.** The newly saved reference postflight does not fabricate the absent original DUT post-reference postflight.

Eight distinct stage files exactly match the final recovery result:

1. `PREFLIGHT_ENTER`
2. `SEALED_TERMINALS_ADMITTED`
3. `BEFORE_REFERENCE_IMPORT`
4. `BEFORE_RECIPE`
5. `RECIPE_COMPLETE`
6. `REFERENCE_ARTIFACTS_SAVED`
7. `COMPARISON_COMPLETE`
8. `POSTFLIGHT_COMPLETE`

The source writes each unique stage with file fsync, same-directory rename and directory fsync; ordinary exceptions attempt a failure marker, while hard termination can leave the last completed marker. This is source-bound durability, not independently observed OS syscall tracing. Public stage projections preserve sequence, details and relative/delta CPU/wall times, omitting process IDs and absolute clock origins.

## Separate budget and actual resource receipts

The new reference-only job had its own approved **180 CPU-second / 240 wall-second** envelope, one CPU, one fresh worker, no DUT jobs and no automatic retry. Child limits are 160 CPU / 200 wall seconds; aggregate work stops at 170 CPU seconds with a ten-second cleanup reserve. The original r3 limit was not extended. Historical r2+r3 used 170.664200952 CPU seconds; the separate proposed 180-second cap is additional bounded work, not a rewrite of those failed attempts.

Actual aggregate use was **43.305812158 CPU seconds / 43.317565786 wall seconds**. The durable recipe interval was 41.472475776 CPU seconds; archived comparison was 0.103416832 CPU seconds. These are one reference-recovery resource receipt, not DUT performance or a controlled speedup. In particular, the new recipe duration cannot retrospectively locate the old r3 kill.

The sampled parent-plus-live-tree RSS high-water was **332,771,328 bytes** (224 samples, 215 live-tree samples, nominal 0.2-second interval). It is **not an exact continuous peak**. Separately, the reaped child maximum RSS was 319,229,952 bytes, not an aggregate-tree maximum; final parent RSS was 14,065,664 bytes. The 2 GiB address-space limit is per-process and the 1 GiB combined-RSS guard is sampled, not hard aggregate/cgroup containment. The supervisor recorded exit 0, verified owned-group cleanup, no remaining group and no uncertainty. Its cleanup SIGKILL entry does not change the child's already observed successful exit status.

The independent audit rehashed 1,210 config pins, 28 frozen members and three operand prefixes; all **46 new artifacts / 2,227,484 bytes** and **89 old artifacts** remained unchanged. The parent output-usage snapshot precedes its own final write and is not the final artifact-directory total. The actual audit was a pure-file audit, with no reviewer DUT/reference execution. Its exact original SHA-256 is `d5bdbd43fd10c4146a0064dd21ee20f003d84fd787d59093b47b8961e899d64d`.

## Source reconstruction, not executable deployment

Nine new original-byte Python files plus exact existing public files reconstruct **24 files for each revision**: eleven wrapper executables, twelve reused oracle-source/metadata roles and one original test source. Source inputs are not silently sanitized or edited. Private-path preparation/sealing generators are represented by hashes only, explicitly omitted rather than presented as portable copies.

From a repository checkout containing this commit, the packaging utility only copies and verifies bytes; it never imports target modules or executes their tests:

```sh
python -B candidates/qwen2_postterminal_reference_diagnostic/assemble_sources.py --repo-root . --output SOURCE_ONLY_R2 --revision r2
python -B candidates/qwen2_postterminal_reference_diagnostic/assemble_sources.py --repo-root . --output SOURCE_ONLY_R1 --revision r1
python -B candidates/qwen2_postterminal_reference_diagnostic/test_assemble_sources.py
python -B -O candidates/qwen2_postterminal_reference_diagnostic/test_assemble_sources.py
```

Existing output, traversal, symlink, invalid-manifest and byte/hash mismatches are rejected. The packaging tests exercise only inert byte fixtures. Original `test_recovery.py` is included as source, **not run by these commands**. Reconstructed source alone is neither runtime admission nor a reproduction of the private data-backed experiment; do not invoke its launch/worker with fabricated configuration.

`pins/R2_LOGICAL_FILES.json` contains the full ordered 1,210 sanitized pin records. `R1_LOGICAL_FILES_DELTA.json` exactly reconstructs r1's ordered metadata using the R2 file identity and two index replacements. The roles are provenance labels, not resolved filesystem locators or a runnable config. Both manifests pin the base commit and every original source byte. The publication includes only source, relative artifact hash/size metadata and documented summary projections—no tensor/weight/header contents, raw field arrays/events, private paths, GO/one-use ledgers, executable config, process identities or memory maps. Existing historical evidence and canonical task statuses are not edited.
