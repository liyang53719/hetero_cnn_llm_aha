# Exact terminal checks for the replay-identity validation attempt

Prepared for candidate commit `8ba333c76722b47b681be88612b1c6987e34a5f4`, tree
`bd2c110bb63e39a7a3213e6dea5ffb04dc74ab91`. This is an offline verification plan,
not a launch or a prediction of success. Use the actual triggering commit and
run/job identity supplied by GitHub, never the latest main or the historical
successful attempt. If publication chooses a different commit, regenerate the
commit-specific source contracts before checking their hashes.

Reviewed source: `same_host_m128_replay_identity_20261017_freeze_cded2ae5`;
full 465-file map SHA256
`cded2ae582a6387cddce8c8bbc38c2e1df46a4038c1d3460bf7566f3273e5228`.
Emitter SHA256
`f3f842ccc8e68bb34778303c110a6c92d053c0adac37dbc1bcf6dc8a2c9fe84a`.

## 1. GitHub and exact archive acquisition

- Bind repository `liyang53719/hetero_cnn_llm_aha`, push event, main ref, actual
  head SHA, run attempt 1, exact workflow and job, terminal conclusion, run/job
  times, artifact ID/name/size/digest and ZIP SHA256. A completed upload alone
  does not establish numerical or metadata success.
- Verify the downloaded ZIP against GitHub's artifact digest before parsing.
  Reject duplicate members, directories/traversal, links, unexpected names and
  excessive sizes. Preserve the original ZIP and exact member bytes privately.
- Successful eight-member inventory: `summary.json`, `source_hashes.json`,
  `m16_attempt_summary.json`, `full_m16_summary.json`, `producer_summary.json`,
  `full_m128_summary.json`, `stage_exits.json`, `replay_identity.json`.
  A failed attempt can have fewer files; preserve that as partial evidence and
  report which authoritative step was reached instead of inventing missing files.
- Strict UTF-8 JSON: reject duplicate keys, nonfinite values, overflowed floats,
  inappropriate scalar types and malformed/digest fields. The new replay file
  is capped at 2 MiB and must equal sorted compact JSON plus newline exactly.

## 2. Existing source, numerical and ownership receipt chain

- `source_hashes.json.inputs` equals the reviewed M128 input-contract's complete
  464-entry map. Its 423-entry composed template equals the reviewed static map.
  The input contract itself completes the independently audited 465 raw files.
- Rebuild both SOURCE_CONTRACT bytes from their exact static maps and actual
  triggering commit: M16 360 static plus contract = 361; M128 423 plus contract
  = 424. Hash each complete map with sorted compact JSON plus newline and match
  its full receipt's validation.source_manifest_sha256.
- All public CI objects equal the actual commit/run/attempt. Both full receipts
  and the producer summary share the current nonce where emitted; never import
  a prior attempt's nonce, producer, runtime, source contract or M16 success.
- Require M16 attempt success; M16 full status
  `PASS_FRESH_SAME_HOST_M16_ASSIGNED27`; M128 producer status
  `PASS_FRESH_M128_PRODUCER`; M128 full status
  `PASS_FRESH_SAME_HOST_M128_ASSIGNED27`. Exact integers are required for child
  PID/exit fields, with positive PID and exit zero.
- Both full validations: rows 16/128, source count 361/424 respectively,
  assigned gates 27, observed stages 28, diagnostic FP32 stages 1,
  owner jobs 17, public completions 21, attention capture fields 10,
  fixed arithmetic and observed official gates passed. Reconstruct each
  source-defined CHILD_RESULT and match child_result_sha256.
- Match M128 producer qualification hash, M16 prerequisite hash, nonce and child
  identity across the public producer/full receipts. The safe producer summary
  is a projection: its own file SHA is NOT the private qualification SHA.
- Six M128 journal phases in order: fresh_producer,
  independent_m128_verifier, m128_git_worktree, m128_compose, m128_seal,
  full_m128. Each must report observed/final integer exit zero and strict owned
  cleanup completion. The first two equal producer_summary.stages; full child
  PID equals the final phase PID. The M16 journal body remains private, so its
  digest is a commitment rather than a publicly replayable journal.
- Validate timing diagnostics as bounded finite nonnegative wall/user/system
  values, with correct source labels. Aggregate child CPU is not proof of
  throttling, speedup attribution or any changed numerical budget.
- Strict cleanup proof bodies are not uploaded. Verify the source-bound
  requirement that successful boundaries validated them, but distinguish the
  program's receipt from independently replaying absent raw process proofs.

## 3. New final authority checks

Require `summary.json` to have all of:
- status `PASS_FRESH_SAME_HOST_M128_ASSIGNED27`, phase `complete`;
- full_m16_prerequisite_pass, producer128_qualified,
  full_m128_assigned27_pass, replay_identity_ready and
  owned_groups_cleanup_complete exactly true;
- failure_kind, replay_identity_failure, producer_failure_observation and
  full_m128_failure_diagnostic all null;
- replay_identity_sha256 equal SHA256 of the exact replay_identity.json bytes.

Require replay_identity.json exact top-level fields: schema, status, identity,
identity_sha256, provenance and authority. Its schema is
`qwen2-same-host-replay-identity-v1`; status is
`IDENTITY_METADATA_REQUIRES_PARENT_COMPLETION`. Its authority has numerical,
freeze, full29, RTL and hardware acceptance false, and both parent requirements
true. This is intentional: the successful outer receipt grants the qualified
readiness, not the metadata file alone. Recompute identity_sha256 from exact
canonical identity bytes independently of the whole-file hash.

An orphan metadata file plus a failed/missing parent receipt remains not ready,
including a file emitted just before post-write deadline expiry. A metadata
failure after full_m128_summary was written retains the numerical milestone;
it must not be upgraded to freeze readiness or silently treated as numerical
failure. Report only the safe declared phase/class/allowlisted code, otherwise
UNKNOWN, without raw exception messages.

## 4. Publicly checkable provenance equalities

- provenance.ci equals the actual CI identity everywhere.
- raw_source_map_sha256 = canonical SHA256(source_hashes.inputs), 464 entries.
- m16_composed_source_map_sha256 and m128_composed_source_map_sha256 equal the
  rebuilt actual-commit 361/424 maps and corresponding validation hashes.
- qualification_sha256 = producer_summary.producer_qualification_sha256 =
  full_m128_summary.producer_receipt_sha256.
- m16_prerequisite_sha256 equals producer_summary and full_m128_summary values.
- producer_manifest_sha256['128'] = producer_summary.producer_manifest_sha256;
  verifier_receipt_sha256 = producer_summary.verifier_receipt_sha256.
- m16_full_receipt_sha256 and m128_full_receipt_sha256 equal the exact respective
  uploaded full summary bytes. Their m16/m128_summary_sha256 and snapshot hashes
  equal each full receipt's validation fields. These summary hashes identify
  PRIVATE numerical summaries, not the uploaded parent receipts.
- m128_child_result_sha256 = full_m128_summary.child_result_sha256, also verified
  by source-defined child-result reconstruction.
- emitter_sha256 and each driver SHA match the actual audited source map;
  wheel_lock_sha256 matches the pinned complete wheel lock. Check recipe source
  hashes, model revision, config and payload ledger directly against that map.
- Validate observed runtime versions, source-enforced settings labels, compiler
  executable/banner hashes and bounded parsed version, all scalar/library
  build identities and the directly rehashed shared combined ELF metadata.
  The shared ELF is required for both row counts. Opaque private context,
  M16 producer manifest and native-result hashes remain commitments unless a
  second public field independently binds them; do not claim their absent
  private bodies were independently replayed.

## 5. Stable tensor inventory and scope

Check exact source-derived keys, types, dimensions, byte counts, encodings,
layouts and logical ID resolution; no heuristic mapping or implied direct-byte
verification of metadata-only providers. Both identity.runs['16'] and ['128']
must contain:
- 13 selected BF16 payload records and 3 readonly records;
- 116 native exports, indexed by BF16/FP32 x official/independent x 29 stages;
- 22 scalar raw outputs per sequential/reduced role and 29 sequential exports;
- full.persisted_actual 20 records (19 sealed outputs plus SiLU);
- 10 attention fields, each with raw, presence and frequency byte identities;
- 28 actual-stage logical mappings, 14 loaded-provider identities;
- 28 comparison bindings per reference method, exactly 27 assigned official
  BF16 verdicts; 21 fixed arithmetic bindings (15 whole outputs plus six
  explicitly observed nodes).

Loaded x is directly rehashed. The other 13 providers retain qualified snapshot
hashes and deterministic source-bound expansion/transpose/padding recipes.
Native original storage identity is qualified metadata where available;
independent native original storage is explicitly NOT_EMITTED_BY_PRODUCER.
FP32 exports stay diagnostic. For Q/K compare the source-defined byte
permutation; kv is K plane followed by V plane. Table cos/sin identities remain
reference-table data, not actual engine output.

Cross-check gate actual/reference hashes and their logical references. Keep
file_sha256, canonical content_sha256, observed-present-content hashes and
full sentinel-containing storage hashes separate. Payload/table equality and
stimulus rows/token/position recipe must be consistent across both runs.

For scores/logits/prob/softmax_fp32: M16 observes 1,632 of 3,072 positions;
M128 observes 99,072 of 196,608. Future counts are 1,440 and 97,536. Presence,
frequency, sentinel identity and causal mapping must agree. Fixed-scalar causal
softmax_fp32 bit exactness has no approved official FP32 tolerance. The explicit
mask remains unobserved. Full29, RTL execution, hardware acceptance and inherited
old PASS remain false in all receipts.

The public manifest enables later regenerated bytes to be compared to retained
historical content hashes. It does not itself reproduce absent tensor bytes or
perform RTL execution. Preserve the original eight JSON bytes, artifact metadata,
source proof, this verification result and explicit remaining limitations in a
new safe archive only after the actual attempt is independently checked.
