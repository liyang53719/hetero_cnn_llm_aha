# Same-job fresh producer and full M16

This source-only launch package joins the frozen official producer supervisor
and the reviewed same-host M16 entry in one hosted job. No production result is
included. A future observed PASS is limited to the original assigned 27 official
M16 gates, 28 observed stages (one FP32 diagnostic), and linked Public21 software
execution. It cannot establish full 29-node acceptance, full M128, RTL execution,
hardware acceptance, or a utilization claim.

## Invocation and authority

The one-shot workflow is `.github/workflows/portable-same-host-m16-launch-r1.yml`.
Publishing that exact path to main starts a job and is a separate launch action.
Only root may approve/publish the workflow after reviewing the source closure.
The workflow checks out its actual triggering commit, admits only the first push
attempt, and uses official actions pinned to immutable commits. The source map
includes the exact workflow bytes. Publishing only the non-trigger source files
is safe, but source validation remains incomplete until that exact workflow file
is present. No workflow_dispatch, retry, or artifact-resume path is provided.

Production command (inside the approved workflow only):

```
timeout --signal=TERM --kill-after=10s 1940s python -I -B candidates/qwen2_resident_matrix/portable_same_host_m16_launch/run.py --root "$GITHUB_WORKSPACE" --out "$RUNNER_TEMP/portable-same-host-m16-r1-private"
```

The cold source command is safe and performs no installation, download, native
compilation, model operation, or consumer run:

```
python -I -B candidates/qwen2_resident_matrix/portable_same_host_m16_launch/run.py --root "$PWD" --cold-source-check
```

This calls the production source-preflight loaders without unittest. It reports
the actual local interpreter and does not claim hosted-runtime qualification.
Production requires normal isolated Python 3.12.15, a measured hosted loader,
and the exact private virtual environment. The reviewed launcher successor explicitly imports `importlib.machinery`, so both
its direct source boundary and the separate original verifier process load the
source guard without ambient test imports. This is a one-line stdlib bootstrap
fix plus a regenerated launch contract; original stages, ownership and numerical
code are unchanged. The historical published freeze is retained as evidence.
The new parent and worker also import the stdlib module explicitly. No stage,
argument, execution shim, or environment monkeypatch is used.

## Ownership and sequence

1. The true combined parent directly calls the frozen producer supervisor. It
   provisions the private pinned environment, reruns the unchanged tiny consumer,
   owns one official/scalar M16 producer, and separately owns the original full
   array/native-gate verifier. All stage exits and cleanup must succeed before
   it creates the exact same-host producer qualification.
2. The same parent uses the original retained-leader helper to create a genuine
   detached Git worktree at the current triggering commit. A fresh composition
   child uses the unchanged reviewed composer and exact static 356-file closure,
   then adds the newly generated actual-commit SOURCE_CONTRACT (357 total files).
   The Git identity and scalar reference tracked in HEAD remain intact.
3. A separate fresh sealing process imports only the composed tree, checks the
   live parent, same host/boot, CI identity, nonce, producer qualification, current
   interpreter/compiler, fresh tiny result and compile receipt, and all original
   array/source bindings. Its receipt is data, not permission to execute.
4. A fresh isolated full-M16 child uses the same venv and four-thread environment,
   configures the original backend once, and invokes the reviewed original entry.
   It retains the original arithmetic, 27 assigned gates, diagnostic FP32 policy,
   both independent references, and full producer 29-node/116-export validation.
5. The parent observes the actual zero exit while retaining process identity,
   cleans the owned group before reap, independently runs the original terminal
   validator, and binds its result to the child, sources, snapshot, and producer
   qualification. A child JSON PASS alone cannot qualify the attempt.

All source imports reject source bytecode caches, unpinned initializers, extension
shadows, foreign source namespaces, changed hashes, path aliases, and historical
contract substitution. No ISA override or historical AVX512 PASS is inherited.
Workspaces must be fresh and disjoint from executing source. Every expensive
stage is single-attempt. There is no implicit retry or deadline extension.

## Absolute budgets and reserves

- Producer setup: frozen in-process alarms at 890-second work, 899 cleanup,
  and 900 receipt deadline. In this combined ownership model there is no separate
  external setup-only watchdog. The true parent calls the frozen supervisor
  directly; the external process watchdog covers the combined 1940/1950 limit.
- Composition and admission: at most 120 seconds, with 10 seconds reserved for
  cleanup/receipt; reduced or rejected when needed to preserve the complete
  later 930-second envelope
- Full M16: exactly 900 numeric, 924 work, 929 cleanup, 930 outer seconds
- Combined: external TERM at 1940, KILL at 1950; 40-minute job, 33-minute run step

These are caps rather than additive guaranteed allocations. The full-M16 phase
starts only if all 930 seconds fit before combined TERM. A slow preceding stage
fails closed rather than shortening numeric work or extending the total. Before and after provisioning,
admission requires four available CPUs, 8 GiB available memory, and 8 GiB free
disk. Frozen setup also checks its own resource floor. Historical M16 timing is
not a fresh hosted performance guarantee; timeout remains a failed attempt.

## Evidence and privacy

The workflow uploads only five exact sanitized JSON files from `evidence/`:
`summary.json`, `source_hashes.json`, `producer_summary.json`,
`full_m16_summary.json`, and `stage_exits.json`. Optional phase files may be absent
on an early failure. Logs, model weights, exports, native arrays, runtime paths,
and private snapshots stay private. Failure evidence records phase, exception
class, actual child exit, final reap status, and cleanup status without dumping
private exception messages. Runtime receipts preserve all claim limits.

## Cold verification

The source package includes stdlib control tests for both new modules. These use
synthetic receipt/orchestration fixtures and real tiny stdlib subprocesses only.
They include zero/nonzero exit, timeout, parent cancellation, unrelated-child
isolation, cleanup failure, exact parent context/manifest binding, current-commit
composition, independent original terminal validation, and minimal isolated CLI
startup. Cold tests also pass under optimization. Workflow static tests and a
separate disposable local Git/worktree composition probe are supplied with the
freeze evidence, outside production payload. None proves fresh numerical PASS.
