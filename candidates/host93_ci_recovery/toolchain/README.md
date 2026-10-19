# Fresh CI Verilator toolchain component

Status: SOURCE candidate with cold and synthetic tests only. No source archive was downloaded, no installed tool was executed, and no real toolchain or RTL was built during preparation.

## Coordinator interface

Load `ci_toolchain.py` from a size/SHA256-checked buffer using Python `-I -S -B`, with `__name__` different from `__main__`. Keep `SOURCE_PINS.json` next to it. Call:

`run(repo: Path, work: Path, call_phase)`

`repo` is the already verified checkout. `work` must be an absent, absolute private directory outside the checkout and the component package. The coordinator supplies:

`call_phase(name, argv, cwd, environment, limits)`

Its result is `{record, raw_log, usage, evidence_root}`, where `record.exit_code == 0`, `record.cleanup_confirmed is True`, and `raw_log` is private bytes. It must throw on failure and use the published five-function WNOWAIT/four-observer supervisor, inherited single-CPU affinity, and shared absolute 6600-second job deadline. This component has no process-launch or network API of its own. Its acquisition child embeds the already pinned acquisition module bytes and does not use the old CLI main or any old review bindings.

## Fixed sequence

1. Observe the required image tools privately before network/output. Missing tools fail; there is no package install, alternate tool, retry, or fallback.
2. Acquire the fixed official Verilator revision `4e194cc3ec8e27b18e17f80d7f99c15f984bbdae`, using the published exact official API/redirect/prefix contract. Independently check all 473 paths, sizes, original data modes and Git blob identities again.
3. Copy into a new 473-file tree using independent inodes. Verify the original `src/V3ProtectLib.cpp` is 22417 bytes/SHA256 `bddc3100c2ce83d7a4fe4656b0ff33cca1be70ea9a8295037c6aea72bc0ec6c1`; apply the unique constructor initializer change; require 22430 bytes/SHA256 `380f292c6e82ce30cd7c0b3375ac3f2b91e5c1e872a2c733ca6d0490122cf6fb`. No original or 929-file object tree is reused, and the uninitialized source is never built.
4. Qualify five onsite tools with five versions and five finite generation probes. The exact onsite versions are recorded; autoconf and autom4te must match. Ubuntu 24.04's onsite version is not misrepresented as the old staged 2.72. Generated probe scripts/C are never executed.
5. Run autoconf, configure, and one fresh `make -j1 opt` with fixed commands and limits. Verify all immutable source members before and after each phase.
6. Use only the new backend for version, hierarchical generation, C++ compile/link, and exact tiny run. Recheck same-job backend, configured includes, wrappers, host programs, and fixed fixtures at each relevant boundary. The finite hierarchy/initializer witness comes from three exactly projected published functions and the pinned initialization contract.

## ccache exclusion

The fixed official `configure.ac` (33835 bytes, SHA256 `e9c0af2019ff3e2786596fccf4ed5b90048cead25c5ee385d033285a5d330e88`) calls `AC_CHECK_PROG(OBJCACHE,ccache,ccache)` at line 298 and invokes ccache's version only under a nonempty `OBJCACHE` guard at lines 299–301.

The explicit environment binds both `OBJCACHE` and `ac_cv_prog_OBJCACHE` to empty strings. Before executing generated configure, a finite same-job check requires the known `${ac_cv_prog_OBJCACHE+y}` cache-hit branch, an exact report-only hit body, the assignment `OBJCACHE=$ac_cv_prog_OBJCACHE`, and the retained nonempty version guard. In POSIX shell, an existing empty cache variable still expands `${name+y}` to `y`, so the search branch is skipped. Any unknown rendering fails before configure. Following configure, each fixed input template's `@OBJCACHE@` assignment must correspond to an exactly empty generated assignment. The fixed `src/Makefile_obj.in` line 45 is `OBJCACHE ?= @OBJCACHE@`. Presence of an unused ccache binary in the runner image is not itself a failure.

## Return value and private artifacts

The JSON-friendly result contains `backend={path,bytes,sha256,mode}`, `verilator_root`, and `host_programs={invoked_path:{path,bytes,sha256,mode}}`. The latter includes `/usr/bin/{autoconf,autom4te,bison,flex,m4,gcc,g++,make,ar,perl,python3}` and `/bin/sh`.

`configured_runtime={path,bytes,sha256}` pins the same-job private runtime JSON. That JSON contains `include`, a complete bounded include-tree inventory, and `wrappers`, with identities for `verilator` and `verilator_includer`. The downstream host stage must read/verify this pin and retain its own checks around generation, compilation and launch. Use its own fresh HOME/TMPDIR and explicit tool environment. No local reviewer path, prior actual binary, or historical acceptance is an input.

Raw logs, complete inventories, acquired archive/source, generated source, tool identities, and process evidence stay under private work/evidence roots. The coordinator should expose only selected stage metrics and scope-limited outcomes. A tiny success is not production-host or full-system RTL evidence.

## Cold validation

`python -I -S -B test_toolchain_cold.py --repo /absolute/verified/checkout`

The suite includes complete 18-phase synthetic callback orchestration, seven early-flag rejection combinations, all 473 mocked blob checks, real small-file exact-patch IO only, source pin checks, source read race/type boundaries, cache disabling checks, timeout/failure-style propagation without retries, runtime/initializer drift rejection, and fixed tiny output checks. Synthetic placeholders are never executed and are deleted with their temporary test directories.


## New narrow CI transport delta
Only fixed acquisition phases inherit the existing proxy/CA variable allowlist verbatim; values are never included in receipts or public evidence. Native phases remain clean. No direct fallback or credential setup exists.
