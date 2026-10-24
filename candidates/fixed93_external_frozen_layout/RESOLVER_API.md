# Readonly external frozen layout API (preparation, no execution authority)

New stdlib-only overlay/frozen_layout.py exports load(candidate, manifest=None).
An explicit checked manifest is passed by preflight/admission. Runtime load without one verifies SOURCE_MANIFEST.json against QWEN2_FIXED93_SOURCE_MANIFEST_SHA256 before opening the new manifest-pinned FROZEN_EXTERNAL_LAYOUT.json. Its exact files must equal the existing manifest-pinned contract/FROZEN_DATA_COPIES.json files. Exactly76 files,30 reference payloads,46 other files; two canonical/disjoint external roots only.

Returned layout API:
- contains(logical): exact membership only.
- path(logical): exact declared canonical regular file, nlink1, initial stat identity unchanged; no hash or payload open.
- logical(path): reverse exact file identity to logical name.
- input_directory: external input root / typed; reference_directory: reference root / first.
- identity(logical, reference_opened=False): 1MiB same-FD streaming hash against manifest bytes/SHA, stamps before/after plus named-path identity.
- read(logical, reference_opened=False): same validation, returns bytes; reference payload denies unless explicitly opened after existing seal.
- stat_reference(logical): exact30 reference payloads only, stat before/after; no payload open.
- install_write_guard(): permanent audit hook rejects writes/mutations/links whose resolved path touches either frozen root; no disable API. Not an OS sandbox or protection against arbitrary native syscalls/preexisting writable descriptors.
- frozen_roots: tuple of two canonical Path roots for output disjointness.

Runtime recipe keeps ROOT as candidate/source. Add frozen_path(name) resolving only the76 exact frozen logical names, otherwise original local ROOT/name, and frozen_name(path) for reverse logging. Do not map arbitrary directory prefixes. Logical data/reference argv remain original exact strings; external physical paths are never used as source/record identities. Metadata checked via safe_path uses layout for exact76 only. Reference bytes remain gated by original OracleGate.open_after_seal; recipe read must pass explicit opened policy only from existing postseal code, not set it globally.
