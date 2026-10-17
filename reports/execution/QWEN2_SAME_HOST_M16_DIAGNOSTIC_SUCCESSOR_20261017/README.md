# Parent-only producer failure diagnostic successor

The actual second hosted attempt, run 38998662188 on commit 902680a0b042ec9b99a7a845c8716662e30503aa,
passed checkout, private venv, pinned provisioning, package inventory and fresh
fixed cases. Its producer child exited 1 and owned cleanup completed. The four
uploaded JSON files and artifact digest are preserved in SECOND_ATTEMPT_FAILURE.json.
They do not contain the private child traceback, so the exact child cause remains
unknown. This revision adds observability; it does not claim a numerical repair
or inherit a previous qualification.

## Narrow change

After a parent-observed nonzero producer exit and completed cleanup, the parent
may read only its current exclusive output's fixed producer.log. A dedicated
reader reads at most 65,536 bytes and rejects symlinks, hardlinks, oversized files,
open races and drift. No producer/log-controlled path selects an input.

The source-bound stdlib parser emits only a fixed code, an explicitly allowlisted
terminal exception class, and at most 8 known source-relative frames with pinned
SHA256 and valid line numbers. It never returns exception messages, HTTP status,
URLs, function names, source lines, locals, argv, raw excerpts or tensor contents.
All unknown frames are omitted. The returned object always states diagnostic_only
true and origin_authenticated false: printed traceback syntax can be forged.
It is not an acceptance authority or authenticated root-cause proof.

Only a complete single standard Python traceback is supported. Chained/grouped,
malformed, truncated, oversized or unsupported-class output is explicitly
UNAVAILABLE. Argparse-only errors, exec-only frames, native crashes and nested
command failures may therefore remain unlocalized. The diagnostic cannot recover
a discarded nested child exit code, and it never reads nested private logs.

Diagnostics are skipped when less than 2 seconds remain in the existing producer
receipt envelope. Otherwise the local stop is at most 1 second from now and at
least 1 second before the unchanged 900-second receipt deadline. The final deadline
is checked again after best-effort extraction. Parser or source-validation failures
retain the original failure kind, status, exit and cleanup evidence. Diagnostics
cannot create QUALIFICATION.json. Existing summary.json carries the optional
observation, so the workflow's five exact artifact paths are unchanged.

Driver, owned_commands, producer source-lock, gate, original numerical sources,
all stage/cleanup functions, producer argv and deadlines are unchanged. run.py
changes only its two launcher hash constants. The workflow changes one comment
to bind a separately gated fresh attempt. The complete input map is 381 files;
its 356 static composed files remain exact, with the 357th SOURCE_CONTRACT generated
for the actual trigger commit.

## Cold verification

Normal and optimized tests pass: 15 parser, 41 launcher/control, 10 package,
45 combined parent, 22 worker, 10 workflow. Tests include real stdlib failing
subprocesses, sentinel redaction, strict 64 KiB growth handling, retained exit and
cleanup, missing/aliased logs, parser failure and near-deadline summary preservation.
Three fresh isolated source-entry probes pass without unittest or numerical
imports. Genuine disposable Git/worktree composition still produces the exact
357-file closure. Its fixture commit is not a production commit. Local test
Python is 3.12.14; hosted execution still requires 3.12.15.

No packages, weights, native builds, numerical/model runs, CI trigger, publication
or branch update were performed by this source-only successor preparation.

## Publication gate

INSTALL_MAP.json includes the self-triggering workflow and requires the separate
root launch decision. Preserve prior failures and wait for prior CI to be terminal.
Before moving the branch, create the candidate Git objects and authenticate a full
381-path publication proof with the reviewed offline checker, explicit candidate
commit/tree pins, and FULL_SOURCE_HASHES.json. Require PASS with all 381 paths
present and every error/missing/mismatch/incomplete count zero. Local assembled
bytes alone are not publication evidence. Only the actual candidate identity
may bind the next runtime source contract.
