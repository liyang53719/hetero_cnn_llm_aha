# Cold generated/source/plan preflight

Run before publication, from any working directory:

```sh
PYTHONDONTWRITEBYTECODE=1 python -B scripts/check_generated_source_consistency.py \
  --root /absolute/path/to/hetero_cnn_llm_aha \
  --receipt /tmp/hetero-consistency-new.json
```

`--root` is required. `--receipt` is optional because the JSON receipt is always
printed to stdout. Its parent must already exist. The receipt must be new, in
system temp or the repository's Git-ignored `work/` directory. Tracked files,
`generated/`, `.git/`, existing receipts and symlink escapes are rejected.
No directory is created in the repository. If `--receipt` is omitted, there are
no intentional repository writes at all.

The gate runs all checks even after a rejection; it has no refresh or skip
option. A Python audit guard rejects writes outside its dedicated temporary
scratch and rejects subprocess/build-tool execution inside validators.
`-B` also suppresses Python bytecode caches.

## Checks

1. The real `generate_shape_layout_vectors.py --check --root ...` checks all
   three generated shape/layout artifacts, including live source identity.
2. The real `block_checklist.py --root ... validate` validates the plan-byte
   identity, coverage, task state, dependencies and existing evidence.
3. The four active Qwen2 model source gates are exercised, including the traffic
   model's Host pins. The two APIs that embed their source gate inside `report`
   stop at an explicitly guarded boundary before `calculate`/`timing_profile`.
   A changed gate API is rejected rather than used to run the model.
4. Dense-residency `BASE_SHA256`, `SCHEDULE_SHA256` and
   `ATTENTION_EVENT_SHA256` are checked with the runner's existing
   `R.require`/`R.file_sha` helpers. No numerical source is generated or run.
5. The frozen saved-V0 receipt is checked at its exact hash. Its reviewed
   compatibility helper must bind only the two reviewed Host files, preserve
   the original historical hashes, check all other hardware exactly, retain
   the pinned upstream timing identity, and reject enabled/non-boolean
   borrower/loan profiles. No saved bound is calculated.
6. The actual continuous-suite planner must form one complete, unique partition
   of every discovered `*Spec.scala`. The four runnable groups and two
   frozen-actual groups are checked explicitly.
7. Only the final Python receipt builder from `run_continuous_ci_gate.sh` is
   executed against synthetic logs in temp. It must record both external
   groups as `NOT_EXECUTED_REQUIRES_FROZEN_ACTUAL_FIXTURE`,
   `counted_as_pass=false`, with dedicated runners; they cannot enter executed
   groups or pass totals. The shell gate, fixture packers, Scala tests and RTL
   do not run. These synthetic receipt counts are not test-execution evidence.
8. Three current-runtime v3 gates bind Matrix-service, prefix-arithmetic and
   the observation inventory to the reviewed default-disabled borrower/loan
   profile. Their current source commit is explicitly null, base commit is
   f16df50, and historical results are not inherited. The original 75-source
   historical receipt remains at its exact immutable hash. Exactly five named
   historical-to-current replacements are admitted; all other 70 hashes stay
   exact. Unknown old/current identities, broadened replacement sets, changed
   receipts, enabled/non-boolean profiles and false execution claims reject.
9. The active official-BF16 and profiled observation helper chain is checked
   with its real `verify_source_snapshot` and `verify_constructor_delta` APIs.
   Helper versions/hashes and the narrow constructor delta remain strict. No
   observer, owner, service or replay is constructed or executed.

Unresolved current-runtime identities are listed separately in
`current_runtime_identity_blockers`. Current guard versions and their reviewed
runtime inventory are distinct from the unchanged historical receipts and
results. There is no global historical refresh or result-inheritance path.

The prefix check is its declared source-hash subgate. Its separate Git-based
arithmetic extraction is deliberately not invoked. The full remote workflow,
numerics, weights, Scala and RTL are never run by this preflight.

## Exit codes

- `0`: every listed cold check passed
- `1`: consistency rejected, including unresolved current-runtime identity contracts
- `2`: invalid arguments or unsafe/unwritable receipt destination
- `3`: missing prerequisite, timeout or validator execution blocked

A passing local receipt is not a full CI run or hardware/numerical acceptance.
Every receipt explicitly records that boundary.

## Cold tests

Once installed as `scripts/check_generated_source_consistency.py` and
`tests/test_generated_source_consistency.py`:

```sh
PYTHONDONTWRITEBYTECODE=1 python -B -m pytest -p no:cacheprovider -q \
  tests/test_generated_source_consistency.py
```

The test fixture uses copied sources and temporary active-model identities.
Its fixture-only active-model setup is not part of the preflight and cannot be
requested through the preflight CLI. The V0 and 75-source historical receipts
are copied unchanged and remain checked at their original immutable hashes.
Tests cover individual generated drifts, all active and downstream pins,
historical/current compatibility rejection, unique partition, false external
pass claims, no refresh, no write/build behavior, receipt safety, and continued
checking after failure.

A test artifact kept outside a checkout can use
`HETERO_PREFLIGHT_TEST_ROOT=/absolute/checkout` to select the source tree. The
script itself still requires `--root` and provides no model-root override.

## CI integration

`qwen2-prefill-model-contract.yml` runs this cold preflight and its normal and
optimized (`python -O`) test variants before the existing model gates. The
original model gates remain required. Workflow path coverage also includes the
preflight, its tests, active source contracts, plan/checklist, generated shape
artifacts, the continuous planner and Scala test sources. The preflight does
not replace any numerical, model, Scala, RTL or full-workflow acceptance gate.
