# CI build-only merged-log context v2 (SOURCE candidate)

This is the isolated v2 SOURCE successor to the frozen context v1 candidate,
which remains held for exactly the two privacy counterexamples described below. It addresses the observed blind spot in Actions run 39187570266:
`fresh_make` naturally exited 2, the receipt reported no timeout, cleanup was
confirmed, and the five-category compiler projection was empty. The actual
compiler failure remains unknown. Those retained actual files and the previous
candidate are unchanged. This package has not been published or executed in CI.

## Narrow change

Only a failed `fresh_make` collects context from its same private `native.log`.
The native runner already merges stdout and stderr into that file; no separate
stderr stream or new native collection is introduced. The existing reader reads
at most the final 1 MiB from a stable regular log, discarding a partial first line
when the read is truncated. It does not load the complete original log.

`sanitize_build_context` retains a consecutive suffix of the last 80 LF-delimited
records, including ordinary unmatched compiler, g++, make, Perl, and bison text.
Relative source and generated-source names are preserved unless a redaction or
length cap applies. A final LF terminates a record; blank records are retained.
Each line is at most 512 printable ASCII characters after sanitization. A longer
line keeps its prefix plus `...[TRUNCATED]`. If needed, oldest complete records
are removed until the entire canonical diagnostics JSON object, including its
final LF, fits within 16 KiB. The remaining context is still a consecutive suffix,
not a selection of category matches. The old fixed observations remain an
optional, independently bounded adjunct; they do not gate context retention.

Finite redaction rules replace URL-shaped values, common credential key/value
and command-option values, authentication/cookie headers, bearer/basic values,
common recognizable token prefixes, long token-like runs, and absolute Unix,
Windows, UNC, or home-relative machine paths. Quoted paths can contain spaces.
Relative source paths are preserved. Long token-like values can conservatively
redact long identifiers or paths. All controls, invalid UTF-8, and non-ASCII
characters become visible ASCII escapes. Redaction precedes line clipping.

PEM-style private-key blocks are redacted record by record. The entire available
1 MiB is scanned before choosing 80 records, so a BEGIN marker earlier in the
window still covers the retained tail. An unmatched END marker conservatively
redacts the available prefix through that marker, including when the matching
BEGIN fell outside the input window. An unmatched BEGIN redacts the remaining
window. This can suppress unrelated context conservatively.

This is a finite diagnostic for the pinned public-source build with its existing
clean native environment. It is not a guarantee of perfect generic secret
removal. Unknown credential formats, unusual path syntax, or arbitrary secrets
embedded in otherwise ordinary short prose may evade pattern redaction. Do not
reuse this mechanism to publish logs from secret-bearing arbitrary workloads.

## Explicit collection state and schema

Each stage's diagnostics has exactly four keys: `observations`,
`merged_log_tail`, `truncated`, and `context_state`.

- `NOT_COLLECTED`: this stage did not collect compiler context.
- `AVAILABLE`: the bounded log was read and sanitized, even if genuinely empty.
- `READ_ERROR`: the fixed private log could not be read or failed its read contract.
- `SANITIZER_ERROR`: source pin/loading, sanitization, or output validation failed.

Non-AVAILABLE states contain no observations or tail and have `truncated=false`.
Exceptions and their potentially private messages are not copied. Collection
failure never replaces the original build exception or changes a failed process
to success. `truncated` covers input-window, line-count, line-length, context-byte,
and old-observation limits. Redaction alone does not mean truncation.

Only `stage_exits.json` changes to schema `host93-ci-stage-exits-v3`; summary and
source hashes remain their v2 schemas. Strict verification enforces exact keys,
finite states, counts, character and canonical byte caps, and permits collected
context only on failed `fresh_make`. Shape verification is not an independent
proof of generic secret removal. Exactly three evidence JSON files remain
publishable, with the same combined 1 MiB cap. Raw logs and native artifacts stay
private. A READY record still requires actual Actions exit zero.

## Unchanged execution boundaries

`ci_support_v3.py`, its SUPPORT_PINS.json, toolchain implementation and source
pins, and original WNOWAIT/sampler sources are byte-for-byte unchanged from the
previous candidate. Existing receipt interpretation, unreaped observations,
cleanup proof, original-exception priority, and phase-deadline handling remain
unchanged. Peak RSS remains the coordinator's cumulative RUSAGE_CHILDREN value,
not a phase-specific instantaneous measurement.

Build-diagnostic mode remains the original 14 acquisition/probe/build stages.
It does not execute the derived backend, tiny model, Host, or numeric path.
No source patch, command, build budget, environment transport, retry, or
postflight acceptance is changed. The existing fresh-make cap remains 3600 total
seconds, 3570 work/CPU seconds, one CPU, 4 GiB AS, 1 GiB FSIZE, and 1 MiB actual
log acceptance. The coordinator's maximum log budget remains 4 MiB. Workflow
policy/publication belongs to the parent and is not supplied by this package.

## Pins and cold results

RUN_PINS.json includes the new sanitizer identity. Its raw bytes are pinned in
run.py. All project module loaders verify size and SHA-256 before compiling the
same verified buffer. Cold loaders likewise pin production source before compile;
run_diagnostics_cold.py pins both its sanitizer and test buffer before either
executes. The reviewed SOURCE manifest identifies the private review package; raw test logs
and local inventories are intentionally excluded from publication.

The affected coordinator/sanitizer suites were rerun in normal `-I -S -B` and
optimized `-I -S -B -O` modes. The four unchanged suites retain the exact v1
source/log identities and carry forward their earlier actual cold results:

- Coordinator: 78 tests in each mode
- Sanitizer: 463 old projection checks plus 727 context checks in each mode
- Unchanged support (v1 evidence): 41 tests in each mode
- Earlier support regressions (v1 evidence): 7 tests in each mode
- Unchanged toolchain (v1 evidence): 41 checks in each mode
- Unchanged transport (v1 evidence): 7 tests in each mode

The tests cover ordinary compiler/generated-source context, paths, credentials,
headers, escaped quoted secrets, PEM boundaries, controls/Unicode, all truncation
caps, explicit state failures, original failed exit preservation, schema changes,
and the unchanged 14-stage build-only boundary. All source mutations and mocked
operations are local to synthetic temporary fixtures. No official source was
downloaded, no native compiler/build/backend/Host command was executed, and no
CI run was started. These are SOURCE/mocked results, not actual build qualification.

Cold entrypoints (repeat each with `-O` after `-B`):

    python3 -I -S -B test_run_cold.py
    python3 -I -S -B run_diagnostics_cold.py
    python3 -I -S -B test_support_v3_cold.py --repo /absolute/project/repository
    python3 -I -S -B test_support_regressions_cold.py
    python3 -I -S -B toolchain/test_toolchain_cold.py --repo /absolute/project/repository
    python3 -I -S -B toolchain/test_transport_cold.py

Independent SOURCE review is complete:
SOURCE_GO_SINGLE_BOUNDED_CI_BUILD_CONTEXT_DIAGNOSTIC_ONLY.
Review manifest SHA256:
9c3c5c60198f421581a186f6b7f1012e058d5e65db8336bdfc3552cad137fe8a.
Review summary SHA256:
ba9d80bf9f08062c378e4c3253b6ed8090e5d5eb6bb002623b48dd6d2a7f2129.
The independent review passed 85 source checks and reran both-mode coordinator
78, legacy sanitizer 463, context 727, four original counterexamples, and twelve
positive controls. The unchanged support/toolchain results were inherited by
identity. The final publication projection still requires its separate content
check. New actual remains NOT_EXECUTED; no build or Host qualification is claimed.

Documentation note: the sanitizer module’s original top-level fixed-prose wording
applies to sanitize_build_diagnostics only. The new sanitize_build_context function
retains bounded ordinary prose under the finite redaction policy described above.

## Preserved v1 HOLD and narrow v2 corrections

The v1 SOURCE HOLD remains unchanged: review manifest SHA256
65c775b7eaf50815a905445445b8f19fe634299199dde5f225659c514d0c6f55;
review summary SHA256
491db3c0e57d000ca703096c099a8880c697d02d9c255773ab5778f9d05c852a.
Its counterexamples are synthetic SOURCE observations, not actual old-log leaks.

F01 expands only the fixed joined GCC path-option table: I, L, isystem, iquote,
include, imacros, idirafter, iprefix, iwithprefixbefore, iwithprefix, isysroot,
MF, MT, MQ, B, and o. Each is tested with Unix/Windows absolute paths and a
relative generated-path positive control. No generic command parser was added.

F02 recognizes credential keys, headers, and options before long token-like
runs are folded. A long key therefore cannot disappear before its short secret
value is redacted. Quoted, unquoted, command-option, and ordinary-text controls
are covered. A token boundary retains bounded matching on degenerate inputs.
Only affected suites were rerun; all unchanged prior evidence is labelled as such.
The coordinator semantics, native runner, WNOWAIT/support, and budgets are unchanged.
