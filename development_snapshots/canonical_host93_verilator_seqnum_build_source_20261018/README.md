# Portable derived Verilator seqnum build source

Pure SOURCE, with all actual machine/review bindings PENDING or UNBOUND. This is a new derived patch to official Verilator commit 4e194cc3ec8e27b18e17f80d7f99c15f984bbdae, not recovered historical code. The original full source is22417B; exactly one constructor-emission line adds m_seqnum{0}, producing22430B. PATCH.json gives paired raw pins and the exact reversible one-line difference. The original official source risk and original generation postflight failure remain preserved.

Public source: https://github.com/verilator/verilator/blob/4e194cc3ec8e27b18e17f80d7f99c15f984bbdae/src/V3ProtectLib.cpp#L338-L340

## File map, provenance and safe history

Exactly nine files: this README, PLAN.json, PATCH.json, ORIGINAL_V3ProtectLib.cpp, DERIVED_V3ProtectLib.cpp, run_seqnum_rebuild.py, load_seqnum_rebuild.py, test_seqnum_rebuild_cold.py and MANIFEST.json. PLAN.publication contains the install destination/map, original production function pins, bounded projection description, excluded material, future-binding requirements and SAFE_HISTORY. Keeping this metadata inside existing files preserves the production review gate's exact eight-members-plus-manifest contract.

The original generation actual was independently confirmed outer exit1/native exit0. Its emitted wrapper had an uninitialized seqnum member. Hash-only historical references are metadata, never live bindings. The new derived build and all subsequent derived backend/micro results are PENDING_AT_FREEZE. No later result is silently inserted into this snapshot. Nothing here qualifies Host93, resolves all possible undefined behavior, or establishes runtime correctness.

## Portable cold use

Use Python -I -S -B, adding -O for the optimized check. The caller first length/SHA-verifies test_seqnum_rebuild_cold.py against the independently reviewed MANIFEST, then compiles exactly that checked buffer with --repo ABSOLUTE_REPOSITORY_PATH. --repo is required and never inferred. The cold suite resolves only four fixed project source dependencies: published build support, its GATE_PLAN, the five-function supervisor source and the four-function observation source. It also resolves the two local patch source files and PATCH.json. It never binds actual roots, reviews, binaries, host tools, inventories or output directories.

The cold suite exercises pure source/mocks and tiny temporary copy files, including a5MB streamed copy. It checks normal/-O corrupt size/SHA rejection before compile, exact source/review pin gates, true original unmodified production PENDING before support/output/spawn, skip3/no hardlinks/mtime, fixed projected buffers and one-unit/link log classification. It never runs make, a compiler, Verilator, a backend, generated code or any subprocess. Synthetic review records are temporary test inputs and do not authorize execution.

## Preserved production logic

Every production function is byte-identical to the frozen derived-build predecessor. Only top-level ORIGINAL/FRESH/EVIDENCE/SUPPORT_PIN and PLAN length/SHA constants are projected. The loader changes only its runner raw pin. Whole-file inverse projection and fixed per-function comparisons are provided outside this package. The cold suite alone adds explicit portable source resolution. There is no replacement lifecycle framework and no binding helper script.

The production loader itself must first be checked for fixed raw length/SHA. Early -I -S -B guards precede project loading. The loader, runner, support and projected function compiles all consume the exact checked raw buffers. No importlib, pyc cache or bare assert safety guard is used. Default --execute-reviewed refuses source review acceptance PENDING before support loading/copy/output/native spawn.

## Future actual binding

PLAN.publication.future_binding_required enumerates the necessary independent original929-file/494646584-byte baseline, reviewed inventory and original build, source/review/dependency-stage records, fresh direct-host identities and explicit path/plan pin propagation. These real checks remain in the production functions; none is replaced by a stub. Zero-size/all-zero-SHA actual placeholders and null records are deliberately unusable until a separately reviewed binding replaces them. The seven direct executable names remain documented but no current OS executable inventory is shipped.

A future source review must bind the resulting exact MANIFEST and verdict SOURCE_GO_DERIVED_SEQNUM_INCREMENTAL_ONLY. An explicit pinned external acceptance JSON may then be supplied by the authorized parent. Publication/source review alone is not native execution authorization. The sole actual executor must preserve the exact outer argv/exit/wall receipt.

The future actual copies the fixed original tree to separate inodes, skipping only V3ProtectLib.o, V3ProtectLib.d and the old backend. It preserves unchanged copied mtime identities, writes the single patch with normal mtime, then runs one original-flags make -j1 opt. It requires one V3ProtectLib translation-unit compile and one backend link, a changed object/backend identity, and no other content delta. The original fixed read-only tools remain bounded prerequisite inputs; no generated configuration rewrite or install target is added. Unexpected work is logged and fails acceptance, with no fallback or rerun.

Preserved limits:900s total,180s preflight,600s work/CPU and latest work stop t780,5s cleanup,115s reserved postflight through t900; one CPU,AS4GiB,FSIZE1GiB,tree768MiB/log1MiB soft acceptance ceilings,at most902 leader samples. Per-process limits are not aggregate hard limits. Leader samples are one PID/starttime; child maxrss is cumulative peak. The fixed WNOWAIT/cleanup supervisor and sampler/usage functions are unchanged. No full build tree, binary/object/PCH, current tool inventory, actual generated wrapper, local argv/log, machine-local path or download is included.
