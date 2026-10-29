# P0 actual compiler dependency evidence — independent source-only review

## Scope and verdict boundary

This is a source/metadata review of a NEW candidate based on actual git object `d4476f8e3fac9a28ea3f475e49f6b68abbac2dbd`; it does not run a compiler, loader, DUT, reference, Torch, EDA, network or CI. The existing frozen artifact/runtime/config is not modified. Tests use real locked source/program metadata but explicitly **mock binary, object, GCC .d, producer receipts and ABI**. A passing test proves the metadata contract accepts/rejects those fixtures; it is **not a real compiler trace, binary derivation, hardware execution or numerical acceptance**.

The intended closure is retained evidence from the independently identified owning producer. Consumer verification does not independently relink object bytes or reconstruct historical filesystem absence. Freshness derives from the reviewed producer implementation, original prebuild source ledger, native owned-stage receipt, and its enforced order; a newly added `fresh=true` or added `files` mapping alone would not establish it.

## Actual d447 baseline, not historical claims

Read-only snapshots are in `source_d447/`; full SHA256 pins are in the review manifest. Source was obtained with `git show`, without checkout or execution.

| Actual source | Lines | Contract established |
|---|---:|---|
| `build_producer.py` | 59–78 | Unique VM_USER_CLASSES driver; exact O0/blank-override/tool argv; host_link target after host archive and three child archives. |
| `build_producer.py` | 90–101 | Clean child environment, native exit 0/errors empty/owned cleanup, output/input pin rechecks. |
| `conditional_admission.py` | 22–49 | Actual complete Host.mk template, unique driver object rule, link target consumes `VK_USER_OBJS` via `$^`. |
| `conditional_admission.py` | 91–120 | Installed compiler inventory binding; actual make closure; existing `native_dependency_guard`; derived input pins. |
| `conditional_admission.py` | 145–151 | Original `FIXED_COMMON_SOURCE_IDENTITY_V1`, generation/source/gate/derived ledgers, physical frontend/SV identity. |
| `native_dependency_guard.py` | 15–23 | Only official Verilator dep names allowed prebuild; driverstem.d is not allowed, and .o/.a/.gch rejected. This is NOT the obsolete blanket “no .d” rule. |
| `one_job_build_only.py` | 71, 90–98, 133–139 | Explicit clean environment; supervised exact argv; admit → prepare → run → pack. |
| `verilated.mk` | 83–99, 124 | Official `-MMD`, NOT `-MP`; CPPFLAGS retains it when CXXFLAGS=-O0. Includes `-I.` and Verilator includes before VM_USER_CFLAGS. |
| `verilated.mk` | 197, 258 | USER_CLASSES→USER_OBJS; host archive does not compile the user driver, so its compilation belongs to host_link. |
| `verilated.mk` | 358–360 | Existing dependency files are read by conditional `include $(DEPS)`; never feed untrusted fixture text into make. |
| `PROGRAM_MANIFEST.json` | 818–820 and extents | Original commands/descriptors hashes and 384/3456-byte spans. These are runtime expectations, not Scala compilation inputs. |

Global make SHA256: `74121398e5be12bf03721f1f0f5ce75e7c703635ec7e50920d43f9c4e31fcc0c`. The retained local official5.032 source exactly matches the d447 tool manifest. Original program manifest SHA256: `4f201e1744b8aa2c604a478ca837076abaf41a7235b62d8aa7ef14fcdc830163`.

## Review findings and fixes requested

1. Early draft only checked make argv prefix/last target. A `VM_USER_OBJS=` injection could satisfy those checks while removing driver linkage. Required exact actual make argv, blank overrides, tools and original hierarchy list; negative tests rehash the containing native receipt, so this is not merely an outer hash failure.
2. Early consumer parsed embedded original program JSON without hashing the embedded text. Required bytes/SHA and original generation path pin before parsing/deriving runtime table expectations.
3. Early .d parser normalized arbitrary Unicode whitespace. Required bounded ASCII, final LF, only backslash-LF continuation, one rule, exact object target, safe lexical paths, no parent traversal, macros, recipes, directives or extra rules.
4. Added collector-code pins must name the actual repo inferred from the existing fixed155/source ledgers, not any unrelated path suffix carrying the desired hash. Original generation ledger must bind the reviewed collector implementation; wrong implementation and wrong repo are independent negative cases.
5. The full record initially risked exceeding the old 64KiB evidence-index cap. The final design keeps that index limit unchanged and pins a separate bounded `DRIVER_DEPENDENCY.json` (2MiB), generated inside the selected runtime bundle, rehashed and compared to the embedded artifact record. Producer/enrich checks the corresponding serialized record cap before packaging. Neither file contains tensor payloads. Real receipt size remains an actual-build obligation; oversized evidence rejects, not numerical acceptance.

## Required unchanged behavior

- Original P0 corrector SHA `3e205b979194d82fc215a1f8c013eff6e009ef79444d05cb20f857db56de3c1d` and locked contract SHA `9a0a4e8e7acb477b48e90afe0fc545d971f9fbaa87cf6586fe090f6f344c41f0` remain independently checked.
- Exact 20→18 DDR observation delta only: gate/up allocations become virtual; impossible PC16/17 observations removed; all other18 observations, inputs, program bytes, addresses/spans, y/cache obligations remain intact.
- Gate/up remain REQUIRED, UNOBSERVED, INCOMPLETE, numeric_pass=false even after successful connection or matching final outputs. P1–4 cannot use this exception.
- Enrichment writes a NEW copied source manifest, embeds and hashes the original text, and preserves all original fields/ledgers. Original source file remains unchanged. Artifact remains exactly seven files; no raw reference/weight/tensor payload publication.
- Runtime program manifest/commands/descriptors are RUNTIME_ONLY / RUNTIME_EXPECTATION_NOT_BUILD_INPUT. Their bytes are later independently decoded/checked by the original corrector; they are not relabeled as compilation inputs.
- AST comparison against actual d447: every `prepare.py` function unchanged. Every run_compare function except `coverage_policy` unchanged; the latter only updates the observation-contract source pin. Original numerical comparator, router baseline, execution and ABI behavior remain unchanged. See `AST_COMPARISON.json`.

## Pending real evidence / stopping boundary

No NEW real .d/native host_link receipt/owning BUILD_ONLY artifact exists in this review. A future authorized build must naturally emit and retain the exact dependency record; absent, stale, oversized, wrong-header, wrong-collector or contradictory evidence must reject. Source-only/mock success cannot retroactively repair the old d447 artifact or justify numerical acceptance. MoE tie policy and FP32/reference arithmetic questions remain pending as before; no tolerance or arithmetic changes are introduced here.

## Independent tests

- `test_auto_hydrate.py`: **16 methods per mode**, normal and `python -O`, ≤256MiB. Full P0 auto hydration → unchanged corrector → exact runtime delta → source links → dependency verification → mandatory load_binding; positive split-directory driver/header; explicit gate/up incomplete status. Negatives cover missing sidecar/evidence, raw program text drift, wrong selected header, rehashed make override, Unicode dependency and non-role normalized-path aliases, old/wrong collector, unrelated producer repo, dependency-file drift/external path/2MiB cap, retained 64KiB index cap. P1–4 preserve original pins/limits and reject P0 exception.
- Independent rerun of candidate `test_driver_dependency.py`: **18 methods per mode**, normal and `-O`; includes producer sequence (stale .o/.d prevents stage; new mock files created only by mocked successful stage; failed stage cannot capture), actual metadata enrichment retention, parser/link/tool/dependency negative cases.
- Total **34 methods per mode**; subcases are not inflated into the method count. ABI verification is mocked, as explicitly declared in the reused connection fixture. No native execution occurs.
- `TEST_DURING_MUTABLE_PIN_REFRESH_*.log` preserves one failed intermediate run while the integrator was updating chained source pins. Failures stopped at `source_guard` with `connection source drift consumer/consumption_proof.py`; these are not silently discarded or presented as passing final tests.

The positive source manifests, receipts, dependency text, native object/binary bytes and owning result in these fixtures are deliberately synthetic. Their role is exercising the verifier, never masquerading as a successful real build.

## Frozen final candidate and exact source locations

**No new concrete blocker in the retained-owning-producer metadata contract.** Candidate `p0_producer_evidence_candidate_20261029T1339/MANIFEST.json` SHA256 `7d792adfd2d72e4a568787c9d57a721379f8b08a60c89e2b06eedc5a01fa2928`; all **53 text members / 347,084 bytes** verified. All **15 actual d447 source deltas** independently recomputed via git show; chained source pins, producer/consumer dependency-verifier identity and old frozen runtime/views/corrector/contract verified. Generated `__pycache__` is explicitly outside the candidate text manifest and was not deleted or modified. Initial verifier cache-enumeration failure is retained in `SNAPSHOT_INITIAL_PYCACHE_ENUMERATION.log`.

Paths below are relative to the candidate `package/candidates/`:

| Source | SHA256 | Exact review points |
|---|---|---|
| `ci_frontend_pipeline_r2_20261029/build_producer.py` | `82aef295be117550be5c7c878f6f70b78d6e195c17061bad0ac292593dd80bfe` | 94–105: absent exact products → original stage success → capture; no command changes. |
| `ci_frontend_pipeline_r2_20261029/driver_dependency_proof.py` | `104326a1630a689f18d6144734fc6142a315c378a42678e41959a27c8a64f278` | 17–30 strict grammar/normalized uniqueness; 32–38 actual capture; 43–46 same-repo collector pins; 50–57 dependencies/header/binary; 58–81 make/tool/argv and frozen receipt linkage. |
| `ci_frontend_pipeline_r2_20261029/p0_source_evidence.py` | `47a126be32385720fd3b3d94e848609f57c24174ea917110bdb1b221d916b800` | 11–15 original source/contracts; 24–27 2MiB metadata cap and drift; 29–33 runtime-only roles; 34–40 retained actual evidence. |
| `ci_frontend_pipeline_r2_20261029/pack_frozen_artifact.py` | `773575951ecf63fca15d5c2082c098a2ca6bd0bc988a3a3df3aaaabba712119c` | NEW source copy with original pins rechecked; actual enriched-byte budget before mkdir; seven-file output. |
| `same_job_materialization_20261029/connect_bundle.py` | `d4aaaeec80b809e19e9d5c4a9163ec4dd7a31b80c3b89a975c4774b9556aed2a` | 21–48 auto hydration and separate pinned dependency metadata; original correction then full source validation before admitted V3. |
| `same_job_materialization_20261029/consumer/consumption_proof.py` | `d4b47498bf0d7c50b90761446edb4d33eb7c5e12a645dc6a40ebcef612a61a4c` | 18–34 original ledger/raw preservation; 35–70 fixed155 and exact compile/constructor; 71–90 frontend role, dep verifier, runtime-only role and actual SV gate. |
| `same_job_materialization_20261029/consumer/observation_contract.py` | `9b9c44af0964cdf2213ce649c5e86dff68ceaa492ec46e4d95b780e4460206db` | 18–45 actual role links and rehashed original program; 47–79 mandatory P0 sidecar, exact delta, P1–4 exclusion, bundle-local dependency metadata, required incomplete gate/up. |

Snapshot result: `EVIDENCE.json`; final normal/-O logs: `TEST_AUTO_NORMAL.log`, `TEST_AUTO_OPTIMIZED.log`, `TEST_PRODUCER_NORMAL.log`, `TEST_PRODUCER_OPTIMIZED.log`. No real native execution or numerical result is implied by any of these artifacts.
