# Reproducible reference-preparation launcher proposal

This is an unexecuted publication template. Cold tests cover control flow and
synthetic receipts; these template bytes did not produce the historical M16
reference artifacts. Historical execution identity belongs only in separately
reviewed safe evidence. A private immutable snapshot preserves the original
executed launcher. This proposal never substitutes its hashes for that snapshot.

The contract has a distinct portable profile and no absolute runtime paths. It
pins the unchanged five asset-proposal files, all five launcher sources, the
original be00 commit and the required interpreter implementation/version, size
and SHA256. The caller supplies `--origin`, a fresh `--workspace`, `--python` and
an independently reviewed `--contract-sha256`. The default CLI is plan-only;
`--execute-reference-preparation` requires separate authorization. The contract
and template alone never grant execution permission.

## Strict identity without published private paths

The interpreter argument must identify the retained origin-venv Python at the
contract's relative location. Normal venv executable symlinks are permitted.
The resolved regular-file size and hash must match the contract. Its lexical
and resolved absolute paths are captured only in private context and launch
receipts, then checked unchanged afterward. The isolated child checks CPython
3.12.14 and the executable hash before importing or invoking the original
producer/backend. Source snapshots, all origin file hashes, original backend
identity, current thread configuration and postflight identities remain strict.
No versions, payload hashes, source gates or admission criteria are relaxed.

Only two existing original reference binaries may execute, with a freshly packed
M16 arena and the authentic retained payload in place. No download, install,
compiler, Public runner, payload copy or fresh native inference is performed.
Native M16 reuse stays explicit; M128 receipts are never relabeled. The original
five-file producer proposal remains unchanged.

## Bound and cancellation semantics

Use a dedicated launcher process without pre-existing children or timers. It
owns a 120-second work alarm including preflight, child work and postflight.
Linux subreaping plus PID/start-time tracking owns descendant process groups.
The parent blocks ALRM/TERM/INT during Popen until child ownership is assigned;
the exec child explicitly unblocks the inherited mask before producer imports.
The original child still enforces its 120-second work and 30-second per-reference
bounds. OMP, MKL and OpenBLAS threads are explicitly four. ATEN, Python, loader
and CPU-dispatch overrides are rejected; unrelated environment is not forwarded.

On failure or cancellation, protected cleanup disarms the work alarm and
ignores repeated ALRM/TERM/INT. The parent sends TERM to the child first, allows
up to five seconds for its own group cleanup, then fallback KILLs and reaps any
still-owned groups. Final evidence publication uses the remaining 126-second
outer ceiling. An external supervisor must preserve the reserve: TERM at120,
KILL no sooner than126. Abrupt supervisor SIGKILL or kernel stalls cannot be
claimed to guarantee cleanup.

## Private receipts and safe publication

Success requires observed zero child exit and no remaining descendants; exact
M16 arena/X hashes; 22 raw outputs for each reference; all29 sequential exports;
logical and token-major shapes; old compile/executable origin; exact new argv;
software ACKs; bounded timings; hashes, source/backend identity and no aliases.
JSON/log parsing is bound to the exact bytes hashed. Failure revokes completion
markers and emits a fixed classification without raw exception text.

Private `LAUNCH_RECEIPT.json` binds the observed child exit, completion marker,
context, both source maps, runtime interpreter identity and exact M16 receipt.
Its hash is in the allowlisted `summary.json`. The caller must separately observe
the launcher's actual zero exit; a process cannot attest its own future exit.
Logs, full receipts and absolute runtime paths stay private. Public output is
limited to status, phase, elapsed time, digests, exit code, artifact counts and
false acceptance claims. Artifact existence alone is never successful admission.

The prepared references remain `REFERENCE_PREPARATION_ONLY_NOT_NUMERICALLY_ADMITTED`.
Packed source/current-native compatibility, strict combined-library provenance
and full linked entry admission remain separate. This template claims no
numerical, full29, actual-chain, backend-order, hardware or RTL acceptance.

## Cold tests

Run the package's `test_launch` unittest module normally and with `-O` in a source
checkout containing the pinned five-file asset proposal. Tests use tiny synthetic
files, mocks and one stdlib-only signal-mask control child. They never invoke the
producer or original binaries, read authentic payload/ELF bytes or change the
completed origin workspace. Runtime paths used in tests are synthetic fixtures.
