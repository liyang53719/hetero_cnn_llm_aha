# Event-only owner lines: portable source/synthetic excerpt

The five files `README.md`, `POLICY.json`, `observer.patch`, `tests.py`, and
`overlay/narrow_fullblock_attention.py` are byte-identical to the frozen 0540
candidate. The unchanged README describes that candidate, not a runnable package
layout. Read this file for the portable layout and test preparation instructions.
The original source manifest contains machine-specific paths and is omitted.
`PORTABLE_MANIFEST.json` contains the finite publication whitelist, relative
source pins, two exact external 0526 baseline pins, and provenance hash references.
This package is not a standalone model runtime or actual execution authority.

## Static verification

From this directory:

```sh
python3 -I -B check.py
```

To additionally verify the exact external 0526 baseline sources and patch:

```sh
python3 -I -B check.py --baseline "$BASELINE_0526"
```

The baseline must contain `narrow_fullblock_attention.py` and
`cached_wholeblock.py` with the exact sizes and hashes in the portable manifest.
No baseline source or model payload is copied into this package. The checker
verifies hashes, whitelist closure, path hygiene and metadata consistency, and
compiles Python sources without importing or executing their module top levels.
It does not execute original tests, DUT, model, native code or any actual run.
Hashes bind bytes but are not signatures or an independent trust root.

## Optional preparation, never automatic test execution

The original tests require a `SOURCE_MANIFEST.json` whose `test_inputs` map uses
resolved local paths. Do not edit the frozen tests or observer to make them run.
Choose a new, nonexistent staging directory outside both this package and the
baseline directory, then run:

```sh
python3 -I -B check.py --baseline "$BASELINE_0526" --prepare-synthetic "$STAGE"
```

After verification, this copies only the exact tests and overlay to the new
staging directory, and generates a fresh local manifest with the three resolved
input paths and exact source hashes. Baseline sources remain in place, read-only.
The generated machine paths occur only in that private staging layout, not in
this publication. The checker prints a quoted original-test command but does
not execute it. The staging directory persists so that command remains usable;
the caller may remove the temporary layout after use. Neither tests nor actual
work was rerun during packaging. Preparation creates no execution authority.

## Reviewed source/synthetic finding

`SUMMARY.json` reports the independent source-only GO, not an independent test
rerun. The author's sealed cold run exited naturally with code 0: 0.816122660
seconds external wall time and 0.745967427 seconds internal wall time. All 14
retained hook consumer bodies produced equal fields, presence, events and fences
on synthetic fixtures. All six scalar anchors retained their 40 fixture slots.
The real shared TraceDispatcher, original Wholeblock listener and an additional
explicitly test-only subscriber demonstrated unchanged other-listener delivery.
The extra subscriber is not a claim about the production subscriber set.

For each 400-tick synthetic variant, both policies delivered 4,400 lines to the
other listener and performed 800 full metadata checks. The recorded approximately
1.12x CPU ratio uses mock metadata; it is not a measured M2 speedup, real native
ABI cost or M128 prediction. The 193 static body positions and 179 non-hook
positions are not measured callback frequency or a 193/14 speed ratio.

Only `__init__` and `_trace` change. The other 28 original method bodies remain
byte-identical, including `_identity`, `_cheap_identity`, `_integrity`, `_line`,
scalar consumers and field/event/fence helpers. All four Matrix hook checks,
all call/return/exception/unknown events, outside-tick and failed-state routes,
tick full checks and final scope cleanup remain on their original paths.

## Explicitly weaker integrity policy

The new local filter skips only normal non-hook lines inside a proven live tick,
with no sticky failure. It retains thread, exact owner, exact tick frame where
applicable and bounded 128-frame active-tick ancestry checks. It does not change
the shared dispatcher's line delivery or other subscribers.

This is not the old per-line anti-tamper contract. Local/context and cheap
client/job/service/profile-object/Dense-binding checks no longer run on filtered
lines. Transient changes restored before the applicable retained hook or event
can escape. Persistent bad Matrix locals reject at the applicable retained hook;
persistent ownership changes reject at the applicable retained identity point.
Detection timing and first-error order can differ. The prior tick-policy
weakening also remains. There is no arbitrary in-process tampering guarantee.

No model/native, actual M2, M128, RTL, full 48-domain, fullblock or numerical
acceptance follows. Any future actual assembly needs its own explicit binding
to the new line policy and prior tick/op policies, separate independent review
and new root authority. The old 0526 authority does not authorize this change.

## Publication boundary

Publish only `publish_whitelist`. No original machine-path manifest, raw review
or cold receipt, admission artifact, log, stream, profile, native binary, runtime
array or model payload is included. Mock fixture literals and array-building
code in the exact test source are not exported model data. The independent
source/synthetic review is 14,374 bytes, SHA-256
`39aa62754886b456d21e69841082f67e58f8389f02acba4c24f4e2d5be087c61`.
Hash references do not make omitted evidence independently reproducible.
The frozen candidates, receipts and external baseline were not modified.
