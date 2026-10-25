# Production M16 Attention component — retained r2/r3 failures, not numerical acceptance

This source/evidence package preserves the first production-component attempt (r2), its exact metadata-qualification repair (r3), and both failed executions. A successful source or persisted-failure audit is **not** a successful numerical run. No performance adoption, full-block validation, M128 success or hardware acceptance follows.

## What was attempted

One fixed-order pair, `original` then `selective_identity_r1`, each uses a genuine M16 public3 Attention component with QK / Softmax / PV commands and the existing production driver, owners, stream writer and native services. QK profile is 2, PV profile is 0; no Dense work or raw-KV transport is requested. M16 component operands are frozen qr/kr/v prefixes, not a newly accepted full public-prefix or full-block result. This is not 128-token prefill and cannot replace the required M128 acceptance.

The candidate combines selective LINE filtering with identity lookup; this is not an isolated cache-only experiment. There is only one fixed-order pair. Until full numerical/reference closure is independently established, retained timing intervals are incomplete diagnostic evidence, not a validated speedup or adoption result. The production EventWriter footer is inside the owner cleanup interval; do not equate this measurement to earlier component-only M2 timings.

## r2 failure, preserved

The attempt remains `FAILED_RETAINED`: aggregate CPU 0.6255341999999999 s, wall 0.6527149829780683 s, child return code 1, verified-owned-group cleanup and no group remaining. It read and unpacked authorized operand prefixes, then failed in the first complete-source `verify_sources` checksum pass, **before project/DUT imports, Matrix ELF load or numerical job submission**. There are no numerical outputs or traces to accept.

The denied resource was the unique restricted-suffix source-metadata member in the 316-file immutable source manifest. It is a 38,536-byte safetensors JSON header envelope with 38,528 JSON bytes, 338 BF16 tensor descriptors and zero tensor payload bytes. Its SHA256 is `124516afba769374e2b948e185dd3e9203e2412daaef3f2ccf7bdbaca0f88987`. This package contains only identity/count metadata, **not the header body, tensor descriptors, weights or any reconstructable weight data**. Whole-checkpoint length/advertised hash are not local weight verification. The exact resource identification is reconstructed from the preserved stack and unique manifest member/order; the original exception did not itself print its path.

The independent r2 review verifies failure closure and retained artifacts; it does not convert r2 to numerical PASS.

## r3 narrow repair, then a separate failed attempt

Only `binding.py`, `policy.py`, `support.py` and `worker.py` differ from r2. The exception is limited to that exact pinned metadata role/path, canonical unaliased read-only access, and an active frame of the registered **original verifier code object** whose current path/root agree. A cloned function with the same name/source/filename but a different code object is denied. There is no suffix/directory whitelist, generic preterminal metadata permission, import-time integrity bypass, or new weight/reference permission. Terminal-only reference and postflight gates remain.

Source-only tests exercised two complete 316-file verifier passes under the actual audit hook, 1,102-pin preflight and terminal-plus-integrity postflight, and wrong-reader/cloned-verifier/write/alias/forged-binary/role/early-reference negatives. Seven focused boundary cases ran normal/-O; the existing 22 source/mock cases also ran normal/-O. These historical file-only checks are not target imports or numerical validation. Original source docstrings referring to a future caller remain byte-for-byte historical source text, not assertions about current admission.

The later r3 attempt also remains `FAILED_RETAINED`: aggregate work-budget exhaustion, child return code -9, retained owned-group cleanup and no group remaining. Parent aggregate CPU is 170.038666752 s, wall 170.08509365702048 s. Both component terminals and output/field material were retained, but independent reference acceptance is **NOT_COMPLETED**. There is no final `RESULT` or complete reference evidence, no numerical acceptance and no postterminal-reference recovery result in this package.

The final independent failure review binds 89 unchanged artifacts totaling 18,197,143 bytes; 1,147 configuration/freeze/input-prefix records (1,102 config pins + 42 freeze members + 3 prefixes), 234,624 causal field-cell checks and 67 executed-module source/code-hash checks. Both actual pc2 jobs have three command completions, one result, final write ACK before owner terminal, service release, 12,976,128 native normal FMAs and zero Dense FMAs. The saved arm outputs/control/ten fields/frequencies agree, and each complete 44,355-event stream parses successfully. Only transient first-appearance native-ticket alpha-renaming is used for comparison; raw streams stay unchanged. A changed-output negative is rejected. This is persisted same-DUT-arm equality, **not independent oracle agreement** or overall run success.

Setup and both terminal runtime qualifications account for the original namespace/Cython audit errors. Their raw `FAIL_MODULE_IDENTITY` ledgers remain unchanged (11/12/12 errors); later bounded qualification does **not** relabel the raw audits PASS. The post-reference runtime inventory is absent.

The last durable worker stage is `RUNTIME_AUDIT_ARM_1_TERMINAL`. No interrupted stack or durable global pair/reference-stage clock was retained. Thus the exact kill position—saved-pair comparison, reference import/execution/comparison, or another postterminal step—is **unproven**. There is no recorded numerical mismatch, but absence of a mismatch record does not show the reference passed. The aggregate CPU includes supervisor and worker-tree accounting; it does not establish that the worker exceeded its 160 s cap. Constituent CPU terms and the exact terminating-signal origin are not recoverable from these receipts. Cleanup evidence is the recorded owned-group check, not a new current process inspection or proof excluding arbitrary group escape. The two complete arm-stage CPU totals sum to 97.267985946 s; the remaining 72.770680806 s is **not a reference-only measurement**.

Recorded owner CPU intervals are 56.895277342 s (original) and 37.679090194 s (candidate), with the fixed order and writer scope above. They are only one incomplete-run stage diagnostic, not a validated speedup. Neither overall FAIL nor reference incompleteness is removed by that observation.

An initial reviewer fixture incorrectly hashed frequency arrays as u32 rather than the original u16 representation and failed before stream comparison. The corrected audit matched the frozen source and retained the initial script/log; no product evidence changed. No DUT/native/oracle arithmetic was rerun by the failure review.

## Limits and evidence boundaries

The unchanged envelope is one CPU, one worker, 180 s aggregate CPU / 240 s wall; child hard CPU 160 s plus parent hard CPU 20 s. Work preserves 10 s CPU / 30 s wall cleanup reserve. AS is 2 GiB per process; combined tree RSS is sampled against 1 GiB, not hard aggregate address-space containment or a continuous peak guarantee. Output partitions are sampled and a per-file limit is hard; all partial evidence remains retained.

For r2 the recorded sampled combined high-water is 35,467,264 bytes; r3 records 284,516,352 bytes. These are sampled observations, **not exact continuous peaks**. The final parent-only RSS and reaped-child maxrss are different metrics; reaped maxrss is not aggregate-tree RSS. Parent output-usage snapshots are taken before the final parent write and are not final artifact totals. Physical processes, argv, maps and raw payloads are not published.

## Exact source reconstruction only

Two manifests reconstruct original bytes from this package plus exact public baseline references at `8c6311401b1fb57e924dbd841e2dc406c904d57a`: r2 has 30 files (29 executable roles plus one candidate source-pin metadata file); r3 has those 30 files plus one original file-only boundary-test source. Fourteen new Python source files preserve the nine new r2 executables, four changed r3 versions and one safe test source. Twenty-one existing-public role references (20 Python roles and one metadata file) are used per revision; duplicate content may serve distinct original roles. Five unchanged r2 new-source files are referenced within this package by r3 rather than copied.

```sh
python -I -B candidates/qwen2_production_attention_diagnostic/assemble_sources.py --revision r2 --repo-root . --output fresh-r2-source
python -I -B candidates/qwen2_production_attention_diagnostic/assemble_sources.py --revision r3 --repo-root . --output fresh-r3-source
```

The helper copies verified bytes only; it never imports target code and rejects traversal, symlinks, changed/missing sources and existing output. It adds only an r2/r3 manifest choice to the previously reviewed packaging utility. Ten packaging-only tests per mode and four revision/mode byte-assembly checks are not model tests. No target/native/original mock rerun occurs during packaging. Original tests/config generators with private absolute literals are hash-only rather than silently modified. The retained boundary-test source still requires private config/input metadata and is **not a self-contained executable test kit**. No header/config/runtime/input payload or execution admission is supplied.

The two ordered logical pin sets retain 1,101 r2 and 1,102 r3 hash/size records without private locators. Raw tensors, events, headers, weights, runtime maps, addresses, credentials, approval records and private config are excluded. Fixed hexadecimal constants in original `component.py` are modeled fixture allocation/table regions, not sampled process addresses or data.

Earlier observer negatives, M2 diagnostic limitations, original M128 CPU-limit FAIL / incomplete acceptance, official reference history and all project task states remain unchanged. No hardware cycles, RTL, utilization or 80/90% goal is established.
