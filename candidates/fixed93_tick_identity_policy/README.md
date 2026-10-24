# Tick-boundary metadata integrity: portable source/synthetic excerpt

The observer overlay, `observer.patch`, `POLICY.json`, `DESIGN.md`, and `tests.py`
are exact original bytes from the frozen 0517 candidate. The original manifest
contains private machine paths and is not included. `PORTABLE_MANIFEST.json`
provides one finite publication whitelist, relative source pins, two external
baseline pins, and reviewed-evidence hash references. This is not a model runtime
or actual execution authority.

## Static checker

From this directory:

```sh
python3 -I -B check.py
```

Optionally verify the exact two external 0503 baseline files and the patch:

```sh
python3 -I -B check.py --baseline "$BASELINE_0503"
```

The baseline directory must contain `narrow_fullblock_attention.py` and
`cached_wholeblock.py`; both are checked by exact size and SHA-256. No old model
payload or baseline source is copied into this publication. The checker hashes,
checks whitelist/path hygiene and compiles Python sources without importing or
executing target code. It does not rerun source tests or actual work. Hashes are
not signatures or an independent trust root.

## Optional preparation for unchanged synthetic tests

Choose a new, nonexistent staging directory outside both this package and the
baseline directory, then run:

```sh
python3 -I -B check.py --baseline "$BASELINE_0503" --prepare-synthetic "$STAGE"
```

The checker first verifies all pins, copies only this package's exact original
`tests.py` and overlay into the new staging directory, then generates a temporary
`SOURCE_MANIFEST.json` with the three resolved input paths and pinned hashes.
The original test and production observer are not rewritten. Both external
baseline files remain in place and read-only. The local resolved paths exist only
in this caller-selected staging layout, never in the published manifest.

A quoted command invoking the original test with its `--baseline` argument is
printed but **not executed**. The staging directory persists after the checker
exits, so the printed command remains usable. The caller may remove the staging
layout after use. This preparation is separate from qualification and grants no
actual execution authority. No test was rerun for this packaging task.

## Source/synthetic finding and important limitation

`SUMMARY.json` records the independently reviewed, limited source/synthetic GO.
The author's original cold run exited naturally with code 0 and reported
0.613357873 seconds internally. It covered 46 controls, all six scalar consumers
and 40 fixture slots with the real TraceDispatcher and dual listeners. This is
not an independent rerun, external wall-time measurement or measured RSS.

For 400 synthetic ticks, full metadata checks changed from 8,400 to 800; the
scalar fixture changed from 46 to 2. These counts describe full-check selection,
not fewer evidence fields, scalar consumers or numerical operations. The mock
ABI timing ratio was approximately 1x, not a demonstrated speed improvement or
measurement of the real 33-symbol ABI snapshot cost. No M2/M128 projection follows.

This is a **changed, weaker metadata-integrity policy**, not old every-callback
integrity equivalence. ABI/profile values changed and restored entirely inside
a tick can evade a full boundary check. Persistent drift at a full boundary still
fails; original cheap ownership predicates remain live at retained callback
locations. The old `_identity` and the other 24 unchanged original method bodies remain
unchanged, as independently reviewed. Only `__init__`, `__exit__`, and `_trace`
change, with new `_cheap_identity` and `_integrity` helpers. The prior
`op-evidence-boundary-v1` exemptions are not silently expanded.

No model/native, M2, M128, RTL, independent numerical oracle or fullblock run was
performed in these source controls. The successor 0526 actual still requires
separate independent review and a root decision as of packaging; this summary
does not claim its PASS or transfer prior actual authority. The unchanged DESIGN
file retains its earlier proposal-status wording; the reviewed source-only
status is stated in SUMMARY, without rewriting historical design text.

## Publication boundary

Publish only `publish_whitelist`. No private original manifest, admission, raw
cold log, result payload, profile, stream, runtime, native binary or model array
is included. Synthetic arrays appearing in the test source are mock fixture code,
not exported model data. The source/synthetic review is 10,718 bytes, SHA-256
`d8314ddec4cda8bc14fbd7edb5542333b407ee5393e670215572f6aa8b842682`.
This hash binds provenance but does not make omitted evidence independently
reproducible. The original frozen sources and receipts were not modified.
