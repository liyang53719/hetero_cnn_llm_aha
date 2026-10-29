# Shared installed runtime — independent source/metadata review

Scope: actual git `fff882f4694fb9c2eea11b361cf40a33a3577b20` plus the three retained installation receipts. This review does NOT install, import Torch, run wrappers/reference/DUT, hash an entire real runtime, or modify the candidate/installed tree. Only bounded text metadata and source are read; tests use tiny mock trees except for three original wrapper text files.

## Actual installed receipts

| Profiles | Runtime | Receipt SHA256 | What it establishes |
|---|---|---|---|
| P0 | qwen2 | `d17376886e9e84b40617ea95fe85da75769f7336ae52f5a111dbfaf887b1814f` | `INSTALLED_ISOLATED_NOT_REFERENCE_TESTED`, 25 runtime wheel identities, actual Python executable pin. Not a complete installed-file ledger. |
| P1/P2 | qwen35_08b | `4a3efb9ea31f19beb8fba3c20021b16b949a78e0540ff1e7b1f739811cf4bbc0` | `PASS_OFFLINE_LOCKED_INSTALL`, installer/lock/tool/merge metadata. Merge manifest covers Transformers only, not every installed dependency. |
| P3/P4 | qwen35_35b | `e093bd9202bf58df274199348044228929e0c8e2b87755eb709ba29b2ab767e4` | Same installation-only scope, distinct original Transformers revision; not reference or numerical qualification. |

At the initial read, all three lack SOURCE_SIDECAR.json. `ACTUAL_INSTALL_METADATA.json` records exact original small-file pins and this observation. No current installed-tree identity is inferred from the receipt alone.

## Independent framework mapping (original RUNTIME_CONTRACT)

- qwen2 → revision `4.40.1`, sidecar SHA `17d159b19e98d6f104bbaba1bd62ea2de96b5bcde8185230135c6a96d445628f`.
- qwen35_08b → `14e738b5d0cc69aa27a95dde272aea41fde44f2f`, sidecar SHA `8a6ba34b3e85bac5427d25a44e97659f6eeaa341392e1bc6d35906434422aada`.
- qwen35_35b → `42ca97014c85d71a88ad60d55f08cb9fb4d26e2c`, sidecar SHA `79078825f230ffecf33fff9b838d40b155217b025accf26e961927a25a475743`.

Original derive_sidecar hashes pinned archive members without imports, and explicitly does not claim complete transitive framework source closure. Its resulting exact sidecar and original installed-module/native verification must be retained. A full installed-tree snapshot adds byte identity / drift detection, not an independent archive derivation for every installed file and not reference PASS transfer.

The actual host interpreter receipts say Python 3.12.14, SHA `fa67443527ed9647f760d807e2a38f26340757123e643c4639cf273ed15d5ea7`. The Qwen2 wheel lock's metadata target says 3.12.15, but the actual original runtime admission only checks Python major/minor 3.12 and x86_64. Do not silently tighten to 3.12.15, label the current interpreter as that patch version, or relax the original ABI gate.

## Import and ownership boundaries

- Original Qwen2 wrapper imports its site-packages, preserves AVX512 capability and 4-thread settings.
- Both Qwen3.5 wrappers import **site-packages + original ROOT/src + ROOT**, preserve default ATEN capability, 1-thread settings and taskset affinity. Their ROOT is an original absolute path. A ledger of site-packages alone misses live import surfaces. Preserve wrapper bytes/interpreter alias and cover all actual import-root bytes, extra/missing files and symlink targets.
- Owner manifest must have an externally supplied expected SHA and fixed 5→3 mapping. Source/receipt hashes in a newly self-hashed document alone are not independent attestation.
- A shared lease must span source verification, reference, P0 RoPE, provider and emit_tsv until wrapper-using subprocess cleanup and postverification complete. No shared-root deletion API; retain evidence on failures.
- Locking is cooperative, not OS-level immutability or proof against uncooperative writers. Pre/post full-byte checks prove snapshots at those boundaries, not an uninterrupted history. Cheap stat checks alone cannot claim unchanged bytes.
- OUT and owner-metadata output must not overlap **any** of the three import roots, not only the selected family. Full identity metadata must not be written into a tree that it snapshots.
- Only after successful postcheck may admitted V3/consumer-success metadata be published. Keep evidence of a failure, but do not leave a success-named consumable bundle from before a failed postcheck.
- Existing 8GiB setup/acquisition gate, Python3.12/x86_64 ABI gate, P0 AVX512 requirement, resource limits and original numerical/reference/comparer semantics remain unchanged.

## Initial candidate findings communicated

1. Draft lease checked OUT only against the selected import_root; another family's directory could be mutated. Requested all-root exclusion before mkdir and bind metadata placement outside all import roots.
2. Draft prepare called connect while inside lease, so final V3 could be published before the context manager postcheck. Requested postcheck-before-publication; connect itself no longer executes the shared wrapper, so it can follow successful lease exit.
3. Shared path bypassed original Python3.12/x86_64 live admission. Requested the same gate, not a stricter patch-version requirement.
4. Top-level docstring said full scans run only on bind while lease actually scans pre/post. Requested precise workload/scope wording.

## Lightweight evidence so far

- `test_wrapper_policy.py`: 3 methods normal/-O, reads only the three original small wrapper texts; CPU/thread drift and wrong Qwen3.5 ROOT rejected. No wrapper execution or interpreter hashing.
- `test_tree_contract.py`: 7 methods normal/-O using tiny temporary text files; detects same-size drift, additional importable module, missing file, alias escape/dangling/root symlink and special file; internal directory alias is recorded without recursion.
- These tests do not prove a real full runtime ledger, derived sidecar or consumer lease has yet been generated/executed. Final frozen candidate verification is recorded below.

## Final frozen review

Candidate manifest SHA256: `b7e77226d9dad578d8e9b6fe09991d6f4dfff7546846ddc5ef6fcca6859a9da1`. Independently verified all **44 text files / 286,291 bytes**, exactly **5 changes** versus actual fff882, and all CONNECTION_SOURCE_PINS. `FINAL_EVIDENCE.json` and `VERIFY_FROZEN.log` contain the checks.

**No remaining concrete metadata incompatibility found.** The earlier all-root OUT / postcheck-publication / ABI / complete native-binding issues are fixed. Exact native argv is linked to the original sample.py SHA, original installation BINDING_R2 source ledger and output/key path; wrong-job same-family receipt is rejected. Original Qwen2 package set/lock and Qwen3.5 exact 11 checks and artifact pins are preserved.

A real-data-only incompatibility was caught during independent stat inspection: original BINDING_R2.source_pins contains a 30,894,944-byte host Python executable, which the draft's blanket 16MiB source limit would reject. Final code uses a separate ≤64MiB limit **only** for the exact pinned interpreter path/size/SHA role; all other source files keep ≤16MiB. No real interpreter body was read here. The other **143 small original source files** were hashed, all matching their original ledger; see `ACTUAL_SOURCE_PIN_CHECK.json`.

Actual installed-tree **names/symlink metadata only** were enumerated: all 8 aliases have existing allowed internal / exact host-Python targets. No real tree file-content scan was performed. The command proposal's actual original derive helper exists and matches `e96130e044520444758b913ba38f7fe774ac752675daf85aaa95da77e136e274`; see `ACTUAL_ALIAS_AND_HELPER_CHECK.json`.

Tests: **20 candidate methods + 3 original wrapper-text methods + 7 tiny-tree methods = 30 per mode**, normal and `python -O`, with 256MiB limit. `CANDIDATE_*.log`, `WRAPPER_POLICY_*_FINAL.log`, `TREE_CONTRACT_*_FINAL.log` are final logs. Tiny-tree / mocked install/native evidence is not actual adoption or reference qualification.

Exact final source pins:
- shared_runtime.py: `e853a724acefd26e7b3ef1f6883003376eaf968b808db505793e731ca0b1d302`.
- prepare_shared_runtime.py: `6dd9a1944ffd956ca96ea8df7924548752c3294c635be5253cbb03943dbcfa82`.
- prepare.py: `7e68337385898059a594c190878c7c238d1dfd2a706b62a83f591375f01bb01a`.
- ADOPTION_BINDING_PROPOSAL.json: `493bb6654e75ba7c20eefcc962a1e1a6bd01e49a2d56af5d5edd5a90e89e5d4a`.

Independent AST check: all original prepare functions except ownership prelude/main are identical; inside materialize, every original statement from payload assignment through reference/provider and final V1 bundle/limits is identical. Original reference/FP32/BF16/MoE/comparator policies are not changed.

## Authorization boundary for the proposed next action

The pinned command is suitable to submit to root for **bounded archive-derived sidecar generation + installed-source/native checking + streaming installed-tree identity creation**, subject to its explicit external owned-group supervisor / RSS / wall / live-byte / disk admission. It is not just a small JSON check: it reads existing archives and hashes installed bytes. It does not install, download, import Torch/framework, execute reference/provider or run DUT.

This review does not itself authorize or execute that command. No actual sidecar/SHARED_RUNTIMES owner SHA is yet available. Any missing/drifting file or resource failure remains fail-closed; installation/source identity must never be relabeled reference/numerical qualification. After successful adoption, the resulting externally pinned owner can be used only with the reviewed lease and original resource/cleanup rules.
