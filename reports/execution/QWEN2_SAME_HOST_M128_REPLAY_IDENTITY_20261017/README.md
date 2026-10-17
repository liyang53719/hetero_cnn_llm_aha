# Same-host M16/M128 actual replay-identity evidence

Independently verified public replay-identity metadata, bounded to the assigned 27 gates and observed causal attention.

## Exact actual run

Commit 8ba333c76722b47b681be88612b1c6987e34a5f4, run 39017864296, attempt 1, job 117353555753, artifact 12095858179. The coordinator authenticated GitHub SUCCESS at 2026-10-17T09:09:38Z.

- Run: https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/39017864296
- Job: https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/39017864296/job/117353555753
- Original artifact: 88,825 bytes; SHA-256 0c25aa1453f5b9f099fdc470933e3074462bd2f92ca08c191a1cfb9adf22b21a
- Replay-identity file: SHA-256 84c4f626331bb68ec6fda0ae53485714c516f6a590a9b6e48a3fcfd41ea5e7fb
- Stable identity body: SHA-256 7fa82000bb935e651f517f77f50c3c37b9be457a81749129500b6e93e71b6562

Exactly eight original JSON files are preserved byte for byte, alongside this README and MANIFEST.json. No old actual-run result is inherited. MANIFEST.json pins the eight original receipts. A separately reviewed ten-file installation map identifies the final archive once frozen.

## Historical numerical result and limits

The current-job M16 prerequisite and fresh M128 producer passed, followed by full same-host M128. Both full receipts report 27 assigned official gates, 28 observed official stages, 17 owner jobs, 21 public completions and 10 attention capture fields. M16 has 16 rows and M128 has 128 rows. Both children report exit 0 and cleanup complete. The same-job nonce is 18a38e39161d6bf82424d15b0ef121437f3b1eda074bd36b5d5c23d38fac4bb5.

The public parent receipt reports replay_identity_ready=true and binds the whole identity file. The identity file alone deliberately grants no freeze or numerical acceptance; parent postflight, publication and deadline requirements still apply. Historical numerical success and offline public-identity verification are separate claims. Full-29 acceptance, RTL execution, hardware acceptance, inherited old PASS and future-job admission remain false. The four partially observed attention stages are scores, logits, prob and softmax_fp32, with causal observations only; explicit_mask_tensor is missing. softmax_fp32 has fixed-scalar bit-exact causal coverage but no approved official FP32 tolerance; it remains diagnostic for official acceptance. No tolerance was expanded.

## Corrected offline verification

The original offline checker rejected provenance.combined_library.source_map_sha256 because its expectation used raw matrix_numeric.cpp SHA-256 7702e5975ff04393deb4969835eb5ffcfbb99258329ee6ac27fd75b289356e14. The source-authenticated tiny-generated compile input is 1ddf017ffda70af19a70385cfffe1d5a405113f27d73378410a7fa2575bcfa25. The correct four-source map is 0e298008babe63514b05405190831b7cf265e6dc82956bef648f9dbbbff36db0, also authenticated by the M16 and M128 composed-source contracts. The old raw map is 802d3495d3c9d08fe7cda8245843e09e359898a00a088cbc7c341b49f91fd0eb.

This is a source-proven expectation bug in the separate offline verifier. The runtime, emitter, actual artifact and original source freezes were not changed, and no numerical rerun occurred. The original rejection and independent source diagnosis remain preserved. The corrected checker derives its expectation from the pinned tiny-generated input contract, rather than copying the observed artifact value. MANIFEST.json records the accepted corrected-checker and independent-review identities when available.

## Retained identities and evidence strength

The original replay_identity.json retains complete model revision/config/payload-ledger identity; deterministic selected-embedding stimulus; token and position ranges; dtype/shape/encoding/layout; canonical content hashes; native and scalar references; actual outputs; capture fields; source-to-tensor and gate bindings; build/compiler/runtime/library identities; and separate provenance. Its stable identity excludes provenance and uses canonical sorted compact JSON plus a final newline. No absent value is invented.

Each rows run retains 13 selected BF16 checkpoint payload tensors; 116 native reference tensors; 22 reduced and 22 sequential scalar records; 29 sequential exports; 28 actual-stage records; 20 persisted actual records; 10 capture fields; and 21 fixed-arithmetic bindings. These counts describe metadata records, not uploaded tensor bodies. Thirteen of the fourteen loaded providers are QUALIFIED_METADATA_ONLY; only loaded-provider x is DIRECT_FILE_REHASH. Separately retained checkpoint payload records have their own direct-rehash identities. Those distinct qualifiers must not be conflated.

The archive retains source/input/reference identities and all provenance exactly. The reviewed raw source freeze has 465 files, map SHA-256 cded2ae582a6387cddce8c8bbc38c2e1df46a4038c1d3460bf7566f3273e5228; the authenticated actual-commit publication closure has 471 files. Runtime source maps and reference recipes are recorded in the original metadata. The combined library was shared by M16 and M128; its content/compiler identities and the qualified runtime versions plus pinned complete wheel lock are retained with their original qualifiers.

## What is absent

There are no weights, array bodies, native binaries, private qualification bodies, raw private logs, absolute private paths or raw process cleanup proofs in these ten files. A public hash remains a commitment to an absent body. The source-defined receipt relationships can be checked offline, but reading metadata does not independently replay absent tensors or validate process identities, descendant scans or termination proofs. Whole-checkpoint verification remains false.

A later implementation can regenerate the canonical stimulus and compare regenerated references/outputs against retained identities. This archive performs no regeneration, proves no new numerical result, and grants no RTL/hardware acceptance. Diagnostic timing carries no causal speedup or future-run guarantee.

## Public reconstruction inputs

The exact public source commit is https://github.com/liyang53719/hetero_cnn_llm_aha/commit/8ba333c76722b47b681be88612b1c6987e34a5f4. Reconstruct the source inventory from the original source_hashes.json raw-input map plus the published M128 input contract; MANIFEST.json pins both M16/M128 input contracts and reconstructed source contracts. The published contracts are:

- M128: https://github.com/liyang53719/hetero_cnn_llm_aha/blob/8ba333c76722b47b681be88612b1c6987e34a5f4/candidates/qwen2_resident_matrix/portable_same_host_m128_launch/input-contract.json
- M16: https://github.com/liyang53719/hetero_cnn_llm_aha/blob/8ba333c76722b47b681be88612b1c6987e34a5f4/candidates/qwen2_resident_matrix/portable_same_host_m16_launch/input-contract.json

Use the exact original artifact identified above from the linked run, or the eight byte-exact original JSON retained here, together with these public pinned sources. The corrected portable checker will be published separately; this archive does not require an inaccessible local path as its sole reconstruction input. Checker source hashes and local freeze labels are provenance identifiers, not accessible download URLs. Public source reconstruction and artifact retention do not themselves replace execution of the reviewed corrected checker.

## Safe local packaging checks

The accompanying evidence workspace contains build_verify.py and test_build_verify.py. Run python3 -I -B build_verify.py --verify, then python3 -I -B test_build_verify.py and python3 -I -B -O test_build_verify.py. These use only the Python standard library to verify exact ZIP membership, original bytes, strict JSON, bounded claims, stable identity, readiness gating and deterministic ten-file packaging. They do not import the model, compile native code, install packages, invoke Git, access the network or dispatch CI. The complete corrected offline verifier is separately retained and reviewed.
