# Qwen2 M128 full-block reference result

Status: **PASS_INDEPENDENT_FRESH_FROZEN_REFERENCE_ONLY**.

The reviewed official-AST subset produced all 29 named reference boundaries, then
reproduced them from original raw inputs in a separate fresh process. All 29
exports are byte-identical to bootstrap; every frozen metadata/hash field and the
original 18-field prefix expectations match. This is reference generation and
reproduction only. It is not a DUT, RTL, full-model or complete-official-forward
acceptance result.

## Ordered history

1. Bootstrap v1 failed unsealed at `worker-start`: its legitimate relative guard
   path was rejected by an absolute-only parent-argv check. Torch and numerical
   payload loading had not started; wrapper preflight raw hashes were recorded.
   The failed receipts remain unchanged. Its exact original 13 source files were
   reconstructed after failure and verified against every original pre-run hash;
   that reconstruction was not mislabeled as a pre-run snapshot.
2. After a separately reviewed CLI identity fix and a new parent go, bootstrap v2
   completed in 6.4827s parent wall time. It remained
   unaccepted observations until independent review approved freezing.
3. A separate source revision pinned the independently reviewed 29 records,
   bootstrap manifest/seal, and review. The frozen contract does not accept
   caller-supplied expected hashes. A complete pre-launch source snapshot was kept.
4. A separate single-go frozen run recomputed from raw13, without reading
   bootstrap or producer payloads for arithmetic. It completed in
   6.5125s parent / 6.4031s
   wrapper wall time. Independent final physical-file review found no blockers.
   No automatic retry occurred.

## Exact identity chain

- Bootstrap manifest: 26,353 B; `9eae09cebcfcd7698dd620cf128c7ef28433a70fe4e674781e0b53e179cd493d`
- Bootstrap seal: 7,539 B; `085b0f17dbd39beb1eaf9824cbcd88de22f978ff445aace196b596d5c805e0e0`
- Freeze qualification review: 2,506 B; `b5baa8bdeaa2a4b1faff81fc01a454588164a8ffbc9a2c07057360d80a2f7ddb`
- Frozen contract: 19,978 B; `64835641b2c0c16d83beb75fbcd9d1c83ade8676fbd825f5e6ab646167af723f`
- Executed frozen source manifest: 2,034 B; `f9e8fe245298de1f5497309762fcf1c4155a6a97d2dbf46d28477984b298e952`
- Fresh reference manifest: 26,348 B; `9bcc9863753cac97db373a1b132b58a490f34932cc4f94c77311bbdf038e0d08`
- Fresh seal: 7,524 B; `be4d2ac5c21ebd96a4720bb5e934cb2e6cfa055b5b3098e4d7cfa10fb5012c63`
- Final independent review: 3,401 B; `fad373a176a882087b3f19544c7c71c5f70df09085814b2bbcc1651ed496b3d3`

`SUMMARY.json` provides the exact evidence paths and all 29 native, FP32-export
and fixed-layout SHA256 identities. It contains metadata and hashes, not tensor
arrays. Raw weights, array payloads and runtime binaries remain ignored local
artifacts and are not included in this publication.

## Source and verification scope

The source package is `../qwen2_fullblock_reference_m128/`. Its 14-file execution
inventory and `SOURCE_MANIFEST.json` are unchanged. Its README and admission files
are execution-time documents prepared before fresh reproduction; this separate
sibling report records the later result without rewriting historical receipts or
invalidating the source package's exact-inventory check.

The executed subset retains 27 original plus 11 added Qwen2 AST nodes and 14
activation nodes, with three pinned Torch boundary nodes. Original expressions,
BF16 parameters, native SiLU, mask, cache-copy relations and fixed layouts remain
intact. Native observed strides are retained, including noncontiguous Q/K/cache.
The MLP hooks fire exactly once in order: gate, SiLU, up, product, down. No complete
Qwen2Attention/Decoder forward or DynamicCache execution is claimed. The explicit
rotary cache bound is 256 versus the official configuration's 32768; configuration
equivalence is not claimed.

Normal and optimized cold suites each passed 65 tests; independent source review
repeated both. Final review checked 29 exports plus native mask, raw13, source and
native-runtime identities, all four fresh before/after boundaries, original18
full metadata, parent terminal state, inventories and resource receipts. Original
M128169 and M16188 execution closures remain byte-for-byte unchanged.

## Resources and acceptance limits

The two export payloads total 65,208,320 B. Both complete run directories total
65,440,202 B, under the 72,351,744 B pair cap. Bootstrap/fresh sampled worker-tree
RSS peaks were 577,777,664 B / 577,679,360 B. RSS is a sampled worker-tree guard,
not an OS hard cap or whole-task RSS measure. The 120s work deadline includes
preflight and postflight; a 122s independent watchdog allows bounded cleanup.
There were no remaining descendants; both run log streams were empty.

Reference equality does not establish all29 DUT observation or numerical DUT
acceptance. Existing numerical tolerances are unchanged. `softmax_fp32` remains
`DIAGNOSTIC_NO_APPROVED_FP32_TOLERANCE`, with `passed=null`. There is no new hardware
cycle, bandwidth, utilization or QoR claim, and no inherited old DUT pass.
