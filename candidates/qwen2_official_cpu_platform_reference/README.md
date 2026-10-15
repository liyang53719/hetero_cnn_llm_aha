# New official-AST CI platform reference policy (pending)

This sibling supplies a cold-checkable new-contract capture entry and pending
local evidence validation. It provides no reference approval or DUT authorization. Existing AVX512
expectations and historical failures remain unchanged. No private 29-output
manifest is copied into this source package.

## Scope

The profile is explicitly `avx2-aten-gemm-v1`: ATen capability AVX2,
`mkldnn.enabled=False`, 4 intra-op and 1 inter-op threads, and deterministic
algorithms. ATen selection is not a whole-process ISA ceiling. The contract is
limited to the same fixed CI environment; it does not claim a full system DSO
closure or machine-independent numerical reproducibility.

Original public geometry and dtypes are read from the existing exact-hash pinned
source recipe pins. Old observed output hashes are never the new acceptance
criterion. The official 38 model and 14 activation AST nodes must remain the
original ones. Torch/NumPy/runtime build requirements and six native file hashes
remain source-pinned under the existing explicit profile. Original DUT error
gates are not relaxed, and this policy does not authorize any DUT run.

## Minimal integration contract

1. Independently review the new capture source and source-only closure. A
   separately reviewed launcher supplies the exact external certificate digest;
   the certificate binds this policy digest, actual source digest, run `new01`,
   and one reference-only invocation. There is no default certificate or issuer.
2. Before official arithmetic, call `observe_platform_before(execute=True)` in
   the capture worker. This delegates to the existing CI-only platform_freeze
   observer for the setup-python ELF and *loaded* libpython mappings/stat/hash.
   Do not relax its root/interpreter paths for the different local large ELF.
3. Take the existing source/raw/native/input-proof boundary and backend/runtime
   state before computation. The new capture entry must separate observation
   from old-reference diagnostics. Do not monkeypatch equality, alter old
   expectations, or modify the original legacy capture/failure record.
4. Observe all 29 outputs using the existing reviewed observation formula. Hash
   actual payloads locally, verify write/readback, and preserve geometry, dtype,
   layout and output-byte identities in a new local manifest. Take after-boundary
   and backend state, then call `observe_platform_after(before)` in the *same*
   process. The old comparison remains a fixed-schema diagnostic, including all
   differences; it is not a new-reference rejection condition.
5. `validate(observation, certificate_raw, expected_certificate_sha256=...,
   expected_source_sha256=...)` recomputes source identity, checks certificate
   bytes, fixed geometry/runtime/input identities, and equal before/after
   boundaries. It returns only `VALIDATED_LOCAL_PENDING_REVIEW`. This pure
   metadata check cannot attest that a caller really performed payload I/O or
   consumed a single-use capability. It deliberately does not grant authority,
   mint a freeze, or publish output metadata.
6. `guard.py` now reuses the original bounded supervisor/capability/watchdog.
   `issuer.py` reuses the existing CI issuer and its exact external certificate
   protocol; it cannot issue that certificate itself. `QWEN2_NEW_REFERENCE_RUN`
   selects `new01` or `new02`. Each requires its own externally reviewed single-
   invocation certificate and exclusive namespace. Existing `--validate-only`
   and `--execute` flags and external SHA environment pins remain mandatory.
   `QWEN2_CI_RUNTIME_PROFILE=avx2-aten-gemm-v1` and
   `ATEN_CPU_CAPABILITY=avx2` are required. Frozen mode is rejected.
7. The new lifecycle adds stable Python/libpython file identities to all
   supervisor and worker source/raw/native boundaries. Full process-specific
   loaded mapping observations are checked before/after inside each worker.
   Output remains sealed *unaccepted* bootstrap evidence, with the new contract
   ID and honest legacy comparison. The independent pair entry below compares two complete sealed captures;
   subsequent freeze admission is still required. Original per-worker 120/122-second bounds are unchanged.

The existing pair's 29/29 same-runner result supports the design but cannot be
retroactively represented as libpython-bound evidence: that observer was absent
from those capture boundaries. A new observed before/after identity is required.

## Private observation schema

`schema`, `run_id`, `source_closure_sha256`, `boundary_before`, `boundary_after`,
`platform_before`, `platform_after`, `runtime`, `backend_before`, `backend_after`,
`typed_inputs`, `outputs`, `legacy_comparison` are exact required keys. Outputs
stay local; validators return no hashes, shapes, strides or values. Expected
certificate/source digests are mandatory inputs, never taken from the document
and treated as external approval. The validator checks byte binding only and
explicitly reports that source authority has not been independently verified.

Cold tests: `python -B -m unittest candidates.qwen2_official_cpu_platform_reference.test_validator`
(and the same command with `-O`). They use synthetic metadata and mock platform
observation; they do not import Torch or execute capture.

## Cold new-contract source entry

`capture_source.load(root)` returns a cold derived capture callable, a separate
new observation validator, and a reconstruction proof. It pins both original
source files by their exact digests. The finite allowlist of exact substitutions
is reversible to every original byte and AST; it does not rewrite official math.
The two legacy prior18 gates become diagnostics only in this new contract. The
private result uses `LEGACY_CONTRACT_EQUAL` or `LEGACY_CONTRACT_DIFFERENT` only
after all 18 comparisons actually ran. Unknown/uncompared is never called equal
or different. Existing geometry, finite, mask, cold-cache, BF16 residual/product,
softmax row-sum and budget gates remain. Output write/readback is explicit.

This entry still fails without a live original capability and a recipe declaring
the exact new contract ID. It permits bootstrap only. Its recipe must supply
`observe_platform_before`, `observe_platform_after`, and
`validate_new_observations`. The independent lifecycle accepts only its pending manifest schema; all old
source files remain unchanged.

For a future read audit hook, `validator.platform_read_paths` takes the already
verified resolved Python identity and returns exactly that ELF, fixed libpython,
and `/proc/self/maps`. The proc spelling requires a narrowly scoped read-only
exception before generic symlink canonicalization. No directory or arbitrary
proc permission is justified. Observer source is in this source-only closure.
Tests cold-load the real pinned source, compile it without arithmetic, and verify
that missing capability is rejected before any tensor/input operation.

## Admission and cold checks

The sole executable admission protocol is the existing CI issuer, source-bound
to this sibling. `validator.validate` is only an optional evidence-integrity
check of opaque certificate bytes and returns pending; it defines no alternative
approval schema. Run `python -B -m unittest
candidates.qwen2_official_cpu_platform_reference.test_validator
candidates.qwen2_official_cpu_platform_reference.test_capture_source
candidates.qwen2_official_cpu_platform_reference.test_launch` (also with `-O`).
The real standalone guard defaults to a cold source inventory check; no default
GO, runtime installation, tensor import, or arithmetic is performed. Source
manifest enumerates the exact thirteen sibling source/doc/test files.

The original supervisor has no global file-open deny hook. For later DUT audit
integration, exact Python/libpython and `/proc/self/maps` reads must be installed
from `platform_read_paths` before invoking the observer; no broad directory
permission is supplied. The current sibling imports and default entry are cold-
checked; actual CI-only platform observation cannot be attested by local tests.

## Same-job pair entry

`pair.py` admits two independently issued external certificates for `new01` and
`new02` in the same job. The existing CI prepare and BINDINGS generation occur
once, shared by both fresh captures. Each capture retains the original isolated
120/122-second supervisor. The pair enforces 69 MiB over the entire new WORK,
including root certificate inputs, and validates the actual SEAL and complete
original observation schema. The optional pure `validator.validate` is not its
admission or completion gate.

Comparison directly reads the exported payload bytes; it does not rerun model
operators. Public records use `OUTPUT_00` through `OUTPUT_28` in sorted original
R.NAMES order, distinct from the legacy18 `NODE_00` through `NODE_17`. Results
remain diagnostic and pending, even when all 29 compare equal. No freeze, DUT
execution, detailed private manifest publication, or automatic retry follows.

The fixed workflow `.github/workflows/qwen2-official-cpu-platform-pair.yml` is
included in the actual source closure alongside all thirteen package files.
Pair tests: `python -B -m unittest
candidates.qwen2_official_cpu_platform_reference.test_pair` (also with `-O`).
