# Portable post-terminal cold128 diagnostics

**Portable actual execution: `TEMP_NOT_EXECUTED`.** Synthetic source tests are not
an actual diagnostic, native capture, carried-phase result, numerical acceptance,
or full-run acceptance. Any historical execution of another adapter/source hash
does not transfer to this package.

This package performs a strictly scoped, read-only cold128 diagnostic only after
an independently reviewed handoff proves the original retained execution is
terminal and its original cleanup receipt is complete. It neither reconstructs
process-handle authority nor proves current process-namespace absence. It never
signals or retries the original run and never extends its deadlines.

## Explicit trust inputs, with no private defaults

Both entrypoints require an explicit caller-provided configuration and an
independently reviewed SHA-256 of its exact bytes. Computing a digest from an
unreviewed file does not create authority. The retaining reviewer must verify all
bindings against genuine original evidence before approving any actual use.
`REVIEWED_CONFIG.schema.json` describes the structural format;
`terminal_gate.load_reviewed_config` also enforces exact types, inventories,
cross-field relationships, canonical paths, and strict identity bindings.

`REVIEWED_CONFIG.synthetic.example.json` contains only synthetic identifiers,
placeholder pins and relative paths. It is not a handoff, receipt or runnable
configuration. There is deliberately no supplied real configuration or receipt.

Required bindings:

- Frozen per-run source commit and exact full-driver SHA-256, matched against
  genuine original PLAN and identity receipts. These fields cannot authorize new
  unreviewed driver code or manufacture execution/cleanup authority.
- Repository, original harness/run, raw fixture and NumPy site directories.
- Exact paths, byte extents and SHA-256 hashes for the original PLAN, terminal
  handoff, reference-freeze inventory and official native manifest.
- Retained execution-session identifier, known executor exit code `1`, original
  PID/PPID/process-group/start-ticks/session identity, boot ID and original
  monotonic work-start time.

Relative paths resolve against the configuration file, never the working
repository or current directory. Absolute paths are also accepted. Symlinked
paths or parents, `..`/`.` segments, repeated separators, duplicate JSON keys,
nonfinite numbers, extra/missing fields and pin drift are rejected. The original
frozen PLAN's explicitly pinned compiler-symlink resolution semantics remain
unchanged; that exception is not extended to configuration/evidence/source paths.
Configuration and receipt pins are rechecked after diagnostics.

The configuration cannot change known terminal criteria: original executor
exit `1`, whole-run `INCOMPLETE`, launcher `FAILED`, actual completion `false`,
confirmed complete original cleanup, two complete absence scans anchored to the
original retained leader, barrier-before-reap and no post-reap signals remain
mandatory. Original work, cleanup and outer stops stay at work-start + 10800,
10830 and 11400 seconds respectively. Configured identities are cross-checked
with the original START, LAUNCH, CLEANUP, manifest and PLAN, not treated as
replacement evidence.

## Unchanged sources and numerical gates

The package uses these existing repository-relative implementations, checked
against fixed SHA-256 hashes before use and again afterward. They are not copied
into this directory or replaced by stand-in fixtures:

| Existing source | SHA-256 |
| --- | --- |
| `candidates/qwen35_gdn_prefill/full_compare.py` | `a3de68cba35a649e98fa76ce103731a31c90f79c179d8806232b274c933f3ec1` |
| `scripts/idma_source_export_20261017/strict_cleanup.py` | `30458e67e84c362ff74d69a702624e91bc3c3089600dd36a2469d9ffd6ec4047` |
| `scripts/idma_source_export_20261017/bounded_run.py` | `26039ae437f9296767ee65cf8303146eadfb61a3116f60e9196a4f68f5b0b380` |

The original chronological scan-classifier logic is replayed from its pinned
source without calling its process/cleanup functions during admission. The
bounded runner owns only its newly created diagnostic child, never the original
run. The package compiles verified local terminal-gate bytes rather than trusting
a module-cache or bytecode-cache substitute; original comparison module origin
and source pins are still checked.

Numerical semantics are unchanged: all 16 genuine ordered accepted cold terminals,
all 19 original receipt hashes, generation-1 joint commit/staging provenance,
raw-only initialization, carried-input continuity, original final-identity rules,
progress/companion-summary consistency, official native/fixture/parameter
identity and before/after pins remain required. Node BF16 max/mean thresholds are
0.03125/0.005; output BF16 thresholds are 0.05/0.01; same-input Conv/SiLU uses the
original ULP threshold 1; FP32 state uses atol/rtol 1e-4. Packed prep receives no
threshold. Optional Conv reference arithmetic needs both the CLI flag and the
reviewed original handoff's explicit permission. No thresholds or full-comparison
phase inventory are modified.

Even a completed process reports `numerical_acceptance: null` and
`combined_full_run_acceptance: false`. A completed cold diagnostic reports
`passed: null`, `combined_full_run_acceptance: false`, `full_block_gate_pass: false`
and no carried inference, hardware execution or RTL execution.

## Synthetic verification only

From the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 python -m unittest \
  candidates.qwen35_gdn_prefill.postterminal.test_terminal_gate \
  candidates.qwen35_gdn_prefill.postterminal.test_cold_postterminal \
  candidates.qwen35_gdn_prefill.postterminal.test_launch_cold -v

PYTHONDONTWRITEBYTECODE=1 python -I -S -B \
  candidates/qwen35_gdn_prefill/postterminal/smoke_isolated_handoff.py
```

The unittest suites are package-importable. Their isolated smoke wrapper runs two
real CLI denial paths (missing and unreviewed synthetic handoffs) under `-I -S -B`,
with a strict file-read allowlist and audit denial of model/native imports,
process/network actions and output writes. Its always-active audit hook lives only
inside that isolated smoke process. The cold-unit suite separately installs a
real audit hook enabled by setUpModule and disabled by tearDownModule, enforcing
no-heavy-import/no-process boundaries without affecting later suites; sys.audit
probes test that enforcement without issuing real process or signal operations.
Other tests use synthetic JSON or source AST extraction, never actual tensors,
weights, NPZ data, native models or full-comparison execution.

For CI discovery, explicitly add `postterminal` to
`candidates/qwen35_gdn_prefill/run_tests.py:SOURCE_DIRS`; that runner does not recurse.
Its source-pin collection must also include the two existing helper paths above
outside the candidate directory. Include those paths and the new directory in
relevant CI trigger filters. The `test_launch_cold` suite already discovers and
runs the isolated smoke wrapper; no separate aggregate/model test is necessary
for this source-only suite.

## Entrypoint contract (not execution authorization)

`launch_cold.py` requires `--config`, `--reviewed-config-sha256`,
`--terminal-manifest`, `--reviewed-terminal-sha256`,
`--reviewed-code-pins-sha256`, and a fresh independent `--output-dir`.
The standalone `cold_postterminal.py` additionally requires the same configuration,
terminal and code pins, and uses `--output` instead. `--include-conv` is optional
and remains subject to explicit reviewed handoff permission.

The source-only `CODE_PINS.json` covers the exact three runtime files. Its SHA must
be independently reviewed and passed explicitly; editing runtime code invalidates
it. There are no default handoff paths, plan hashes, source commit identities or
retained-session identifiers in executable production code. An actual run still
requires separate current permission and a genuine reviewed configuration.
