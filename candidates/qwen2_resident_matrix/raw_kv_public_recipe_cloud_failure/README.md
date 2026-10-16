# Public M128: one original cloud-sandbox run, failed inner host budget

This evidence-only checkpoint records the single approved cloud-sandbox run at commit
`be00eb8e4bc75e2e41f2a434d05d4c901ed3faa5`, tree
`07cdd8b1bc7508da7b587fc8465d4e8026f67731`, launch contract
`b4ea311e11a64695fba4ccfc1f512240ddccdbada99710d58a1a36dbe5d1d96b`.
Session `99610` exited `1`; original safe output is `FAILED`, phase `numeric`,
outer elapsed `2762.816418` seconds. There is no Public numerical acceptance,
completed postflight, full-29-node acceptance, Scala execution or RTL execution.
No rerun, timeout enlargement, backend change, workflow edit or push is part of
this checkpoint.

## Observed failure and timing limits

The terminal diagnostic resolves through `PublicCoupled.tick` to the original
2400-second Public host wall-clock guard. In the pinned composed runtime,
`ffn_public/execute_numeric.py:109` checks the deadline and calls
`ffn_drain/check_numeric.py:39`, raising `ValueError` with the source message
`public FFN host budget exceeded`. The guard is line 103 in the clean original
source; the contract-pinned overlays move it to line 109 without changing its
meaning. This is an inner guard failure. The outer result is `FAILED`, not
`TIMEOUT`; no numerical mismatch or completed numerical comparison is reported.

`checkpoint.json` embeds a bounded timing projection supplied by the source-bound
read-only diagnostic review. It includes scalar timing/counter metadata and hashes;
the private report itself is not included. Its original identity is recorded.

- Actual Public host elapsed: `2400.2100579410035` seconds.
- Public prefix host elapsed: `82.37693366200256` seconds.
- Setup elapsed: `335.069335` seconds.
- Last emitted diagnostic: sequence `61`, `FFN`, PC `16`, `REQUEST`,
  `actual_execute` / `ENTERED`, `public_suffix`.
- Last diagnostic clocks: writer `2273.228089879` seconds; phase
  `2261.354416201` seconds. Last diagnostic host ticks: `18,941,741`.
- Final bounded projection host ticks: `19,929,718`. Both records have
  completion `16`, request `15`, owner-result `14`, final result `0`.
  The final projection records contiguous completed PCs `0..15` only.

The writer, phase and inner Public clocks have different origins. The last event
is not an exact final halt timestamp or heartbeat. No exact Attention-only time
or exact FFN remaining budget is asserted. Host ticks are software-model events,
not hardware cycles, MAC utilization or proof of completed FFN arithmetic.
Original setup/inner Public/numeric-envelope/total budgets remain
`900 / 2400 / 2430 / 3420` seconds. The CPU summary's
`ELIGIBLE_FOR_BACKEND_CHECK`, `eligibility_only=true`, `backend_qualified=false`
are preserved; this eligibility record does not establish native backend status.

## Preserved bytes and identity boundary

`safe3/` contains exactly the untouched `summary.json`, `progress.json`, and
`source_hashes.json` from the terminal safe output. SHA256 and byte sizes are
pinned independently by the validator and checkpoint. The artifact source map
contains 285 original identities and 12 generated-overlay identities. The runtime
source map is the original map with those 12 identities replaced; it is different
from the clean original source map. Its canonical SHA256 is
`9d1aa25d2f76aea864c86dbfa7cfc3a724cb2e6bafd2c8f8158d19937f057f33`.
The context identity and per-run diagnostic writer identity are pinned too.
The writer hash is a random run identity, not a source-code hash.

Five local control-record hashes bind session and terminal observation metadata.
The checkpoint does not include their contents, private context, logs, numerical
arrays, weights, venv, libraries, reference outputs or private report. These are
local provenance identities; offline checks do not independently authenticate a
remote CI origin. Optional source checks hash source bytes without importing
code or validating private native receipts. They do not authenticate Git metadata.

This candidate directory is outside the 285-source closure. Existing repository,
source/runtime trees, workflows, launch contracts and frozen evidence are untouched.
Cold-validator success, previous successful results, setup progress, and source
identity checks cannot be inherited as Public PASS.

## Cold verification

From the candidate root (or a repository containing this folder):

```sh
D=candidates/qwen2_resident_matrix/raw_kv_public_recipe_cloud_failure
python3 -B "$D/validate_evidence.py"
python3 -B -m unittest discover -s "$D" -p 'test_*.py' -v
python3 -B -O -m unittest discover -s "$D" -p 'test_*.py' -v
python3 -B -m unittest candidates.qwen2_resident_matrix.raw_kv_public_recipe_cloud_failure.test_evidence -v
python3 -B -O -m unittest candidates.qwen2_resident_matrix.raw_kv_public_recipe_cloud_failure.test_evidence -v
```

Optional read-only source and local provenance verification:

```sh
python3 -B "$D/validate_evidence.py" \
  --source-tree /path/to/clean-original-checkout \
  --runtime-tree /path/to/composed-original-checkout \
  --control-records /path/to/local-control-records
```

The two source roles are deliberately distinct: supplying the composed runtime
as clean original source, or vice versa, is rejected. Source reads are limited to
285 explicitly identified paths, 2 MiB per file and 32 MiB total. Control reads
are limited to five exact named JSONs. No other runtime/private files are read.
All checks use the standard library; they do not execute setup/numerical/native
code, launch subprocesses, run Git, use the network, or import runtime modules.
Enforcement survives `python -O`.

Validation rejects PASS/acceptance inheritance, false/zero confusion, changed
source/context/writer identities, changed original bytes, duplicate/unknown keys,
non-finite/deep/oversized JSON, unsafe paths, symlinks and special files, and
missing/extra files. It reports `FAILED` with all Public acceptance false even
when every cold check succeeds. Tests copy exactly the seven intended files into
a temporary fixture. Use `-B`; caches and every other extra entry are rejected.
