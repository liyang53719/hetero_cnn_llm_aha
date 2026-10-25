# Three fresh-process rotated M2 observer-cost diagnostics — not adoption

## Exact scope and observed result

This add-only source/evidence package preserves one terminal, bounded experiment: three serial fresh processes, each running the same actual M2 attention driver with the original observer, observation disabled, and the `selective_identity_r1` candidate. No model geometry, input, native arithmetic, owner/service/lease schedule or independent reference recipe was replaced. The candidate combines selective LINE filtering **and** identity-key lookup. No candidate is adopted here.

| Physical trio | Actual execution order | Off owner CPU (s) | Original owner CPU (s) | Candidate owner CPU (s) | Candidate / original CPU |
|---|---|---:|---:|---:|---:|
| 0 | off → original → selective_identity_r1 | 0.159542826 | 0.646809977 | 0.407252657 | 0.6296326146496655 |
| 1 | original → selective_identity_r1 → off | 0.155633034 | 0.602959193 | 0.347227548 | 0.5758723841200312 |
| 2 | selective_identity_r1 → off → original | 0.183638306 | 0.742407933 | 0.398697880 | 0.5370334317265438 |

The candidate's measured owner interval CPU was lower in all three pairs: reductions of 37.03673853503345%, 42.41276158799688%, and 46.296656827345615%. Each variant occupied each ordinal position once. **Only three cyclic rotations were measured**, not all six permutations, randomized trials, full carryover balancing, statistical significance, stable speedup, or workload-general adoption evidence. This is the complete candidate versus original, **not isolated cache-only benefit or measured hashing cost**. Earlier selective-only R4 and single-trio identity results are different experiments, not controlled denominators. Wall samples, physical-order links and exact spread are retained in `evidence/EXPERIMENT_RESULT_PROJECTION.json`; no timing extrapolation to M128 is valid.

## Actual evidence and limits

The independent persisted-artifact audit passed 64,530 checks (64,472 data/source and 58 supervisor-receipt checks), retained 347 artifacts totaling 12,835,774 bytes, and rehashed all 1,026 runtime/source/input pins. This packaging does not rerun target, native, original mocks, cold admission, or arithmetic.

- All nine arms retain their own output/scores/writes and full 1,515-event service lifecycle, 216 native tickets, 933,888 native FMAs and owner clock 5,042. Full output/control/lifecycle comparisons passed; **only ticket bijection** is allowed in the comparison view. Raw event files were not sorted, relabeled or rewritten. Public files contain metadata, not raw tensors, events, weights or runtime maps.
- `TRIO_*_RESULT_PROJECTION.json` preserves the actual arm-array order, `execution_order`, `order_index`, `arm_artifacts`, and separately named `canonical_reporting_order`. Canonical comparison does not alter physical artifacts or arm objects.
- All six observed arms' ten fields match their own independent reference byte-for-byte, including presence and shape; observed-arm frequencies match across rounds. Reference normalizer collection repeats 8/16 times versus DUT observation once, with identical value/presence/shape. **Reference observation frequencies are not claimed equal to DUT frequencies.** DUT write counts mean unique first writes; reference write counts mean all collector events.
- Each process starts the independent reference only after all three actual terminals. Its own output and score hashes bind the reference. The reference is the unchanged AST recipe with shared exact RNE primitives, not a complete official Transformers forward. Only causal observed cells count, not padding/sentinels.
- Fifteen runtime snapshots and full module/source identities were reviewed. Compilation was for identity only, not target execution. The artifact manifest is an **external post-run preservation ledger**, not a retroactive run-native standalone final seal.

## Supervision and memory — exact assurance boundary

The parent and all three child receipts are EXITED, with child return codes 0, verified-group cleanup and no group remaining. Recorded aggregate CPU is **18.79356525 s**, aggregate wall **19.15878644003533 s**. Per-round aggregate CPU deltas include supervisor CPU, not isolated worker time.

The reviewed admission allows one CPU, 60 s aggregate CPU / 90 s wall; each serial worker has at most 18 s CPU / 27 s wall. Work checks reserve 2 s CPU / 3 s wall for cleanup. Each process has a 1 GiB `RLIMIT_AS`; source checks sampled combined RSS against 1 GiB. This is **not** a hard aggregate address-space cap or cgroup containment. Source-bound supervisor behavior includes all-task child accounting, retained exited-leader identity until cleanup/reap, verified-own-group signaling, and fallback guards installed even when cleanup/ownership checks raise. No automatic retry is allowed.

**The final RSS 16,633,856 bytes is a supervisor-only point sample after all children were reaped, not peak RSS.** The six before/after samples are also supervisor-only. No live combined-RSS sample history or peak was retained. Lack of sampled rejection **does not independently verify a peak ≤ 1 GiB**. Source and receipt configuration support the policy; there is no separate live affinity/RLIMIT snapshot, complete CPU schedule, memory high-water attestation, parent-launch argv/approval hash or raw wait/reap/syscall trace. Recorded cleanup success is not a complete OS event history. These limitations are retained in the audit projection rather than inferred away.

## Source-only reproducibility

`pins/ASSEMBLY_MANIFEST.json` reconstructs **22 exact original-byte files**: fourteen wrapper executables, four observer modules, one source gate, one observer pin file and two focused-test sources. Four wrapper files changed/new for this experiment (`launch.py`, `worker.py`, `admission.py`, `stability.py`); two historical stdlib test sources are also included. Fifteen unchanged Python files and one metadata file reference the public baseline at commit `e4e97a4e81b52b751129cde8a3932ee28503354d` instead of being duplicated.

From a repository checkout containing this package:

```sh
python -I -B candidates/qwen2_attention_stability_diagnostic/assemble_sources.py --repo-root . --output fresh-source-directory
```

The assembler copies only preverified bytes, rejects traversal/symlinks/missing or changed sources/existing outputs, and never imports or executes assembled target code. Its packaging-only tests use inert source bytes. The two small packaging utilities are copied unchanged from the already-reviewed identity package for a standalone manifest-relative CLI; their exact provenance is listed. Source assembly **does not supply private runtime/input/configuration closure and does not grant execution admission**. Historical target tests are published as source, not run by packaging. Their runner expects fresh `tmp` and `mock` directories and writes test outputs; no automatic native command is provided.

The historical source reviewer reported 1,654 static checks, 52 focused author test executions (26 cases in each mode), 14 independent admission and 12 supervisor mock executions across normal/optimized modes. These distinct sets are not summed as unique tests. Unchanged larger suites were reused, not rerun. The predecessor r1 freeze is preserved; its signal-fallback exception issue was fixed only in this r2 source. Historical pre-execution review wording remains historical, separate from the later actual audit.

## Sanitization and unchanged project status

Physical locators, approval/claim metadata, process/inode/device/address identities, raw tensors/events/maps, private config, weights and runtime dependencies are excluded. All 1,026 ordered logical pin hash/size records are retained. Projection files explicitly list omissions or logical-role transformations and identify original evidence by hash/size. Source bytes are not rewritten for portability.

Prior buffer diagnostic failure and selective fixture slowdown, earlier R1 BLOCKED, prior selective/identity actual results and full **M128 CPU-limit FAIL / incomplete acceptance remain unchanged**. No full-block or larger-M validation, RTL, hardware cycles, utilization, 80/90% attainment, performance adoption or task-status promotion follows. The existing Chinese canonical plan may link this scoped result separately; this package itself makes no canonical task edits.
