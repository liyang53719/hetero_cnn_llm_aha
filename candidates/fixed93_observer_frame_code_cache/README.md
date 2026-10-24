# Portable callback-local frame-code cache source excerpt

This whitelist contains two source overlays, two relative patches, their original
relative baseline pins, a portable synthetic test, and a static checker. It is
not an independently complete model runtime, an admission, or a performance or
numerical PASS. No runtime, native binary, tensor/array data artifact, private
absolute path, or raw cold log is included.

## Scope

Only `TraceDispatcher._dispatch` and
`Fixed93FullblockAttentionObservation._trace` acquire an initial
`code = frame.f_code` binding. Their remaining direct reads use `code`; the
six and fifteen lexical sites respectively become one site per callback.
Parent-frame reads remain unchanged. There is no cross-callback cache, new
filter, identity-frequency reduction, audit-hook edit, numeric change, or
record/schema change. The native 33-function inventory helper and existing
`op-evidence-boundary-v1` logic are preserved.

Python's [official frame documentation](https://docs.python.org/3.12/reference/datamodel.html#frame.f_code)
classifies `f_code` as read-only and documents its `object.__getattr__` audit
event. The new read count is intentionally lower on applicable paths. This is
not equivalent under arbitrary stateful, mutating, counting, or raising audit
hooks, nor unrestricted introspection. Known source-pinned guards ignore that
event. No runtime speedup is claimed by this packaging revision.

## Provenance and publication boundary

`PORTABLE_MANIFEST.json` contains the exact publication whitelist, file sizes
and hashes, seven relative test-input pins, and the frozen source-manifest
SHA-256. It is a portable derivative, not the original full manifest. The
original full manifest and cold receipts are deliberately not shipped.

Both overlays, both patches, and `BASE_PINS.json` are byte-identical to their
frozen counterparts. `BASE_PINS.json` already uses only relative source paths;
it is retained unchanged as provenance, not a claim that every referenced
historical source is included. The public README and checker are packaging
artifacts. The sole test-source modification replaces the original PINS lookup
with CLI-root resolution and eager size/SHA-256 checks for all seven inputs;
all test bodies are unchanged. No target code or tests were run to package this
revision. The checker validates itself against its manifest hash, not a
cryptographic signature or independent trust root.

## Static checker

From this directory, run:

```sh
python3 -I -B check.py
```

This verifies whitelist closure, UTF-8 source, file pins, path hygiene, unchanged
source pins, and Python parsing without executing target or test code. It
explicitly reports external inputs as unchecked when no roots are supplied.
For complete input-pin, inverse-module-AST, and exact relative-patch checks:

```sh
python3 -I -B check.py --baseline "$BASELINE" --old-observer "$OLD_OBSERVER"
```

`BASELINE` must point to the caller-provided exact pinned 0300 source root;
`OLD_OBSERVER` must point to the exact pinned 0417 observer source file. That
file's parent must contain pinned `m2_io.py`. The baseline root must supply
`capture/wholeblock.py`, `frozen_layout.py`, and
`source/candidates/qwen2_resident_matrix/ffn_public/check_prefix_numeric.py`.
No external directory is searched or substituted. All seven input files are
individually size/hash checked before synthetic test construction.

## Optional synthetic test

On a Linux CPython environment that supports CPU affinity and resource limits:

```sh
python3 -I -B tests.py --baseline "$BASELINE" --old-observer "$OLD_OBSERVER"
```

This is the frozen synthetic-only contract test with portable pin loading. It
compiles pinned sources and instantiates selected observer CodeTypes against
mock objects and operations; it does not import or execute model modules or
native kernels. Its small arrays are synthetic in-memory fixtures, not model
data. The output is synthetic-only evidence and must not be presented as real
M2/M128 throughput, numerical validation, or execution authorization. Running
this command is separate from the static checker and was not done during this
packaging task.

Apply patches only to disposable copies of the exact pinned baselines. Never
modify frozen sources. Publish only files named in `publish_whitelist`.
