# Full M128 frame-routing integration: public SOURCE excerpt

This is a small, review-only SOURCE excerpt, not a complete independently
runnable assembly, deployment bundle, runtime, or actual-execution authorization.
The copied Python sources, two policy JSON files, relative support pins, and
runner patch are byte-for-byte unchanged from the frozen source package. No
source sanitization, rewriting, generated substitute implementation, runtime
copy, or weight copy was performed. Supplemental documentation and the static
checker are new and separately pinned.

## What the source represents

The full original pc0..20 runner is preserved: original prefix pc0..8, live KV
append, M128 Attention, original live tail, all public21 completions, algorithm
and trace seals, then the original official-reference gate and numeric
comparisons. The supplied runner patch changes only the report's integrity-policy
binding. It does not insert a startup break, M2/M16 driver, historical comparison,
partial fullblock result, or sampled timing profiler.

The frame-routing policy deliberately reduces transient integrity sampling on
skipped off-hook owner lines. A mutation restored before a retained boundary is
not guaranteed detected, and a failure may be detected later. This is not
identical to the predecessor's per-line anti-tampering contract. Event schema,
14 retained owner-line hooks, six scalar returns, SiLU paths and control/exception
events are retained. Exact loaded observer source and identity checks cover a
finite direct-source closure, not arbitrary transitive standard-library behavior.

The raw-source loading changes remain bound to the policy, source manifest,
review, factory/bind and seal checks. Original one-use factory-purpose and DUT
closure checks remain. The sources containing admission logic do not grant
permission merely by being present in this excerpt.

## Proposal, not permission or a completion guarantee

The proposal is 43,200 total seconds = 43,185 shared work + 5 cleanup + 10 final
supervisor reserve, with one CPU and a 2 GiB process address-space limit.
Shared work includes loading, input hashes, complete pc0..20 computation,
reseals and postseal reference comparisons. No extra comparison time is implied.
Calibration is not a guarantee that computation, comparison, cleanup or all
receipts finish within this budget.

The fresh free-space gate is 22,715,767,588 bytes: owned reservation
22,178,896,676 bytes plus unchanged separate margin 536,870,912 bytes. The original
1-second sampler and 2,048-byte row bound imply 43,201 rows and 88,475,648 bytes.
Stream, field, record, raw, metadata and file caps are not reduced. Aggregate
output/RSS are sampled checks, not hard instantaneous group quotas. The original
6,600-second authority does not authorize the proposed longer duration.

## Evidence boundary

The upstream frozen-source record reports 41 source controls and source checks
covering 74 observer functions under target CPython 3.12.14, elapsed
0.6712374799972167 seconds and maximum RSS 35,348 KiB. That work did not import a
DUT or run native/model computation. The existing independent review accepted
only the source-cold scope for one metadata materialization. These historical
records are summarized here, not rerun or republished as raw evidence.

At this excerpt's freeze, a separate metadata assembly had been materialized
(555 files, 8,900,809 bytes). Its fresh full preflight/cold review was still
pending. Neither that assembly nor a claim about its eventual cold result is
included. Separate fresh review and source/budget/policy-bound root ADMISSION
are required for actual execution. Prior M2/M16 calibration, startup checks,
source controls, and this package's static check are not a fullblock pass,
numerical PASS, or inherited actual authorization.

## Included and intentionally absent

PACKAGE_ALLOWLIST.txt is the exact public file allowlist. PUBLIC_MANIFEST.json
pins every included file except itself; its trusted SHA-256 must be obtained
out of band. SOURCE_PINS.json identifies the copied files by package-relative
path, size and SHA-256 and records upstream source/review fingerprints. The
relative pins in the original policies and SUPPORT_PINS.json may name dependencies
that are intentionally absent; they do not imply a dependency-complete bundle.

Excluded: raw BUDGET_PROPOSAL, CONTROL_INPUT_PINS, raw receipts/logs/ADMISSION,
private machine paths, input/reference payloads, arrays, actual event/output
streams, external runtime/ELF/Git payloads, model weights and old-run evidence.
The source text includes ordinary identifiers for these missing dependencies,
not their data. The literal '/root/' in two verifier functions is solely the
logical reviewer-agent namespace prefix, not a filesystem path; it is preserved
as verified source and is narrowly checked as such.

## Safe static check only

Run `python -I -S -B static_check.py` with trusted CPython 3.12.14. This reads only
this excerpt, checks the exact allowlist, sizes and hashes, parses JSON and Python
ASTs, and compiles Python sources in memory without executing their code. It does
not import the excerpt modules, create bytecode, write output, invoke a child,
perform a network request, read model data, or run original tests or builders.
Optional `--source-root` and `--review-file` arguments permit read-only upstream
fingerprint/copy verification when those private originals are already available.
No machine path is needed in, or saved into, the public package.

Do not execute source_controls.py, prepare_fullblock.py, any overlay module,
preflight, original tests, DUT, native/model work, or an actual fullblock from
this excerpt. The only executed file during excerpt verification is the new
static checker. A static PASS means byte/structure consistency only.

For precision, unchanged generic platform constants (filesystem root, procfs
locations, a process-stat suffix, and the fixed system-command search path) are
also present in source. These are not private machine locations. The checker
narrowly allowlists the existing absolute-looking string constants and retains
the logical root-authority tokens and author-task-name exclusion exactly.
