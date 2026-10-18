# Host93 fixed firtool archive and single-member reproduction

This source-only package preserves the reviewed acquisition gate, one-member helper and synthetic tests without changing their bytes. It includes no archive, binary, runtime log, machine-specific command line or system inventory. A later firtool execution is a separate stage and authorization.

## Reproduce the source checks

Use the project-relative dependencies and commands in INSTALL_MAP.json. The original published acquisition code and firtool plan are reused unchanged. The gate verifies source SHA/size before same-buffer compile/exec, and its direct cold entrypoint uses `python -I -S -B`, repeated with `-O`. The tests also project only the fixed published FakeOS class from its checked raw source. No project importlib or bytecode cache loader is used. The original candidate passed24 normal and24 optimized tiny/mock tests; the member boundary review added16 cases in each mode. This projection only checks byte identity, not another actual acquisition.

Default preflight launches no child and performs no network request. Actual acquisition requires explicit approval, the guarded execution switch and a fresh private output outside the repository. The only network target is the fixed official Maven1.62.1 artifact in GATE_PLAN and the original plan. Default platform HTTPS/TLS and inherited proxy configuration remain untouched. No credential settings, redirect, direct fallback, retry, tool install or binary execution is added.

## Shared180-second limit

Preflight, source freezing, download, ZIP validation, member hashing and writing share an entry+170s work deadline. Original WNOWAIT private-group cleanup has at most5s. Parent postflight and final receipt remain within entry+180s. No extraction phase receives a fresh deadline. The original acquirer's internal elapsed-check180s remains, but the outer work deadline covers the complete child earlier.

One Python child uses CPU affinity1, RLIMIT_CPU170s, RLIMIT_AS512MiB, RLIMIT_FSIZE64MiB and no core dump. Socket timeout is30s. Archive acquisition must observe EOF before its64MiB read cap; member bytes are capped32MiB. Log64KiB is an acceptance check after cleanup, not a realtime log limit. The parent Python has no new AS cap; these are child limits rather than cgroup limits.

## Exact member and failure contract

The official archive is pinned to SHA63acdcb58ed12d4c1aa0ecdedc6e2425a252e94eefb75df9253c118d7d222039. The sole allowlisted member is org.chipsalliance/llvm-firtool/linux-x64/bin/firtool, pinned to SHA7f52d2a3782d09736895f66e7eb0e5cc4b3b1b18aa1ad0d04fca4cd6e42cd2ee. The helper parses the exact archive buffer whose SHA was verified. It does not hash a path and then reopen it as ZIP.

At most4096 directory entries are admitted. Absolute/escaping/ambiguous paths, duplicate names, symlinks, special entries, encryption, missing/directory members, CRC failures, wrong SHA or size limits reject. Only the fixed output basename firtool is written; no archive path is joined to a filesystem destination and extractall is never used. Member bytes are checked before an exclusive no-follow0600 write. There is no chmod or execution. Interrupted writes may remain for evidence but cannot become accepted success.

The opaque acquisition receipt retains its original meaning. The member receipt and outer RESULT are both non-terminal. Parent postflight requires exactly four regular artifact files, fixed member bytes/SHA/mode, receipt binding and frozen source identity. Cleanup warning residue is conservatively rejected, without rewriting the committed receipt or retrying. Success requires the independently observed original outer exit0, elapsed within180s and a complete actual acquisition/member identity review. A residual receipt alone is insufficient.

SAFE_HISTORY.json records the observed first attempt's exit0/5.827s,8,763,451-byte archive and25,009,456-byte non-executable member. Its independent actual review is intentionally PENDING at this freeze. No firtool version probe, RTL conversion, Host execution or numerical qualification is claimed. The original plan's size=null describes its prior knowledge, while the separate safe history records the later observation.
