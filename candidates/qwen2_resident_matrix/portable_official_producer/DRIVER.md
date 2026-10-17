# Fresh official M16 producer driver

Source-reviewed proposal, not a completed producer run. The driver is a new
same-host profile and never inherits the older AVX512 producer PASS. It does not
launch the public actual chain, M128, RTL, or a full model.

## Parent contract

The caller must run in an isolated fresh Python 3.12.15 environment with `-I -B`,
no existing source bytecode caches, and the exact selected source-lock closure.
The parent launcher owns fresh same-host tiny-consumer qualification, the live
nonce/context, isolated runtime setup, real process exit and process-group
cleanup, and post-child verification. A serialized producer manifest alone is
not completion or execution permission.

The parent supplies the CLI flags `--root`, `--workspace`, `--deadline-ns`,
`--attempt-nonce`, `--commit`, `--run-id`, `--run-attempt`, `--context`, and
`--context-sha256`. The context is exactly the parent directory's
`PRODUCER_CONTEXT.json`. Its exact bytes bind the actual parent PID, source root,
output directory, source-lock/driver hashes, same host/boot, original absolute
deadline, nonce, CI identity, and fresh tiny-result hash. Output must be disjoint
from the source checkout; source-side output is rejected before creation or
acquisition.

`verify_handoff(root, workspace, manifest_sha256, decode_native=True)` is intended
for the parent's separately owned, isolated verification interpreter. It checks
all artifact hashes, original source identities, actual runtime identity,
compiler and two recipe libraries, fresh payload provenance, original native
metadata, all 116 exports, both independent 22-file reference inventories, and
replays the unchanged original M16 array validator. The array replay is NumPy
validation and does not invoke another framework forward. Keep the same
four-thread environment. No original numerical tolerance or arithmetic is
changed by the wrapper.

## Preserved work

- Exact paired generated runner: d7bd12077675984ed7cc20e57a55729fd62e66b773008fa631673086a5a87a64
- Original official `native_forward`, original `run_gate` arithmetic, 29 stages,
  116 native/independent exports, nine reported semantic checks, and twelve
  recomputed array-semantic checks for each path and precision
- Fresh 13-tensor official layer-0/embedding acquisition using 22 pinned ranges,
  94,382,080 bytes; no full-checkpoint download or copied historical tensors
- Fresh sequential and reduced C++ sources. Their original arithmetic and
  metadata verifier remain unchanged; their numerical comparison verdicts do
  not jointly gate one another
- M16 native phase cap 60 seconds, combined QKV/QK compile phase 30 seconds,
  each scalar compile request 10 seconds and each scalar run request 30 seconds
- Parent total setup/cleanup/receipt envelope remains 890/899/900 seconds

The source lock includes 66 files, including eight package-initializer imports
that were missing in the untested 58-file draft. Driver and lock identities are
bound separately to avoid recursive self-hashes. All locked source contents and
the exact lock bytes are rechecked. Unpinned package initializers and existing
source-side bytecode caches are rejected before numerical-source imports.

`owned_commands.py` executes the byte-exact published process owner and contract
without importing cached bytecode or an unrelated module named `contract`.
External commands use an explicit same-PID exec shim because the published owner
launches Python. It retains the unreaped leader until group cleanup, reserves
six seconds for cleanup, restores control-signal handlers, and rejects nonzero,
interrupted, expired, or unreaped outcomes. Original table generation uses its
unchanged 10-second subprocess API in the producer's inherited process group.

## Cold checks

Run `python -I -B test_driver.py` from an assembled source tree containing the
exact source-lock closure. The 21 tests cover cold imports, JSON/path/context
rejections, exact lock equality, alias rejection, real same-PID exec and signal
unmasking, nonzero/timeout/interruption cleanup, original phase caps, paired-runner
source regeneration, sequential/reduced source/header regeneration, and stale
bytecode/package-initializer rejection. They never download weights, compile
C++, load a recipe ELF, run a framework forward, or claim numeric acceptance.
The C++ source regeneration test uses an explicitly temporary Git source fixture,
not a published commit or producer receipt. Both normal and optimized isolated
cold tests have passed; independent integration review is still required.
