# Fixed M128 metadata source-only replay

This 10-file source-only derivative omits all four generated artifacts from the independently reviewed 14-file candidate. No binary table is encoded as text. This source-derived adapter calls the retained `pack()` and `convert()` directly. It is not recovery of the missing historical C++ headers. Source provenance is repository commit `6bde92d43d2ea9a78e951c0062e133aecf8b091e`, tree `9f743cd7ff48b820ac65ce2bb15024864b37d4e9`; all package source paths are relative and the caller supplies the repository root.

Run in a fresh isolated stdlib Python process:

    python -I -S -B replay_metadata.py --repository /path/to/repository --output /path/to/new-output
    python -I -S -B test_replay.py --repository /path/to/repository
    python -I -S -B -O test_replay.py --repository /path/to/repository

## Actual implementation

- Eight exact project sources are read, individually SHA-256 checked and compiled from that same byte buffer with `compile/exec`. The minimal pattern comes from the pinned source-recovery `test_recovery.py`; the replay has no importlib loader or project cache lookup.
- Six original ABI/descriptor/schedule modules plus the two original metadata packers execute. `heteronpu.__init__` and the public fixture's wider model loader do not execute. Five reference-only source files are separately pinned.
- A finite import shim permits these already loaded modules and the specific stdlib imports they need. NumPy/Torch imports, preloaded numerical libraries and unlisted project imports are rejected.
- The two original `sys.path.insert(0, ROOT/'src')` requests are deliberately suppressed by a local compatibility object; every other argument is rejected. This is an explicit loading adaptation, not a claim of identical top-level import semantics. Real `sys.path` is checked unchanged. This trusted-source routing is not a hostile-code sandbox.
- `pack()` writes only metadata; `convert()` changes seven Dense-B descriptor dtypes to BF16. Its separate numerical `pack_words()` is untouched and never called (profiled by a cold test).
- JSON projection follows `fixture.py`'s four regions and existing allocation fields. `EXPECTED_LAYOUT.json` retains the earlier independent metadata evidence, with tensor-payload digest claims removed. All projected fields, 35 reservations, 2 KV subviews and the 21-command schedule must match exactly.
- No `generated/` directory or generated artifact is distributed. Fresh replay recreates the 384-byte command table, 3456-byte descriptor table, metadata JSON and 2962-byte layout-only C++ header in a caller-selected output directory. Tests verify their original reviewed sizes and SHA-256 hashes, plus exact fields against `EXPECTED_LAYOUT.json`. Metadata replay writes zero tensor payload bytes. The 94,920,448-byte figure is the layout sum for 14 readonly tensors plus the tables, not materialized or verified tensor content.

## Strict limits

The header's regions and Gate/Up reservations are fixture descriptions, not launch admission, resident DDR permissions, memory access permits, initialization evidence, or proof of physical implementation. The header is not placed in `canonical_host` and supplies no loader, `HostMemory`, ownership lifecycle, or native-model stub.

No numerical formula was rewritten; no tensor arrays, native compilation, EDA, producer payload or owner simulation ran. The legacy stream framing, its 1078 framing bytes, stream SHA acceptance, receipt construction, full-block physical admission, all27 numerical acceptance, cycles and QoR remain unrecovered/unproven. Fixture metadata cannot make those gates pass.

Runtime verifies the pinned source subset, not an entire Git repository or live HEAD. `SOURCE_PIN.json` records the verified base commit; `PROJECT_SOURCE_HASHES.json` records this candidate's own files. `TEST_RESULTS.json` records actual cold runs and fresh replay. The replay implementation, source pins and expected layout remain byte-identical to the original reviewed candidate; only the test comparisons and package documentation/receipts change. Polluted-pyc positive controls deliberately execute harmless markers only from disposable temporary caches; the real replay is audited to open none of those project caches.
