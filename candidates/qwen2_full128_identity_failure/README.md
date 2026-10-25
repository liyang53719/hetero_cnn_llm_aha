# Full128 identity-observer integration: CPU failure retained

**The real `identity_m128_02` attempt failed at the original 3,600 CPU-second limit. It is not a numerical or lifecycle PASS.** This is a distinct outcome from `identity_m128_01`, which was rejected during startup admission before DUT computation. Both attempts, the older M128 CPU failure, prior bf16/fp32 failures and canonical task statuses remain unchanged. The separately completed M16 Attention-component reference closure remains valid only in its own scope; it does not imply full128/full-block acceptance.

## Two separate actual outcomes

| Attempt | Recorded outcome | Scope |
|---|---|---|
| `identity_m128_01` | Worker exit 1, 0.05047 reaped CPU s / 0.055217379 wall s; parent-argv claim rejected | Before normal target loading, native Matrix binding, initialization or DUT numerical work, according to pinned call order and traceback. No accepted worker claim or target artifacts. |
| `identity_m128_02` | `FAIL_EXACT_M128_DUT_RETAINED`, reason `sampled_tree_cpu_exceeded`; worker -9 and reaped | Real prefix/Attention work occurred. Sampled tree CPU 3,600.02 s, reaped child user+system CPU 3,600.035657 s, worker wall 3,600.458010603 s. No full terminal or final reference comparison. |

The first root invocation used parent flags `-B -I -S` instead of the strict required order `-I -S -B`. Persisted stderr independently identifies the **compound parent-argv claim check**; exact wrong-order attribution comes from root command history. Raw failed-parent argv and capability bytes were not persisted, so those receipts alone cannot isolate each conjunct of the guard. Its saved child argv was already correct and must not be substituted for missing parent evidence. The consumed claim and all eight first-attempt artifacts remain preserved; no guard was weakened and no claim was deleted/reused.

The successor used a new gate/config/approval identity with the correct parent order. The seven gate sources and profile/interface bytes remained identical. The corrected run passed its one-use worker claim and normal/native loading; persisted `ORIGINAL_PREFIX_COMPLETE` and PCs 0–9 plus the actual event stream establish activity. The orchestration's initial `PREPARED_NOT_EXECUTED` label survived SIGKILL and **must not be mistaken for “nothing executed.”**

## Minimal reviewed source integration

The 0900 source integrates the previously published selective-LINE plus identity-lookup observer with explicit installed/cleaned mask evidence. Relative to the original failed full128 sources, four executable files differ: monitor, service trace, bridge and runner. Monitor/service trace reuse exact public source bytes; **only bridge.py and runner.py are newly added original Python source files here**.

The bridge's new `mask_snapshot` definition matches the separately reviewed M16 source AST. It adds no frame-sensitive callback wrapper and leaves the original driver call, stalls, ACKs, arithmetic, service MRO, stream codec, registry/comparator and terminal-only reference transition unchanged. Ordinary entered-monitor/mask failures are recorded while the original driver and suffix drain to their original terminal before observer acceptance rejects. Constructor/source-binding failures and actual driver faults retain their failure semantics. Explicit KeyboardInterrupt is cancellation, not a drain guarantee; SIGKILL can prevent any final mask/capture artifact.

The runner's only change from its original version is to retain `observation.get('selective_masks')` in evidence. Source/mock review passed 499 source/pin checks and reused 28 author AST/dummy cases per normal/optimized mode, with 18 separate independent AST/dummy cases per mode. These are fake-monitor/dummy-driver source tests, **not actual full128 mask or numerical qualification**. They were not rerun for this publication.

The 0911 configuration composes these exact 0900 sources and explicitly enables the selective observer. The 0941 successor changes only gate identity/associated pins and the root command contract, not numerical code, inputs, original official-reference artifacts, thresholds, admission rules or budgets. Historical preparation flags and legacy static-review `GO_SINGLE_M128_EXACT_DUT` labels are retained as history, not executable authorization or actual acceptance.

## Surviving stream: a deeper partial prefix, not completion

A single bounded read-only pass parsed the immutable **168,738,143-byte** stream, SHA-256 `fb792f566cea3d27640507cd6dfd1f0c3e9e446dcbc12bf3145a4e89d3af26f0`. It found **1,766,012 complete canonical frames**, with EOF exactly at a frame boundary and no partial tail. **There is no END/count/hash footer.** The lifecycle `finish` acceptance was not called. Canonical framing, prefix ordering/debt/ticket/epoch and source-schedule checks found no mismatch only within those surviving frames; none is an arithmetic comparison.

- QK: 5,030 groups started; **5,029 service-completed**, meaning all eight accepts and matching result/done retired.
- PV: **10,352 service-completed**, meaning all token+1 accepts/results, matching done and final legacy reply retired.
- Tokens **0–106**, all twelve query heads, have all eight PV groups retired. At token **107**, heads **0–9** do too.
- Last recorded active position: token **107**, query head **10**, KV head **1**, QK keys **48–63**, profile 2, opcode 35, mask 255, tag 5030. Three of eight scheduled depth steps were accepted, with no result/done for that active group. PV for this head has not appeared.
- Last prior completed ticket is **15409**, epoch 0. The active group's ticket/epoch are unobserved; do not invent a next ticket.
- The last owner event edge is **5,822,096**. This is a software event position, not a hardware-cycle count or the exact instruction at SIGKILL.

“Service-completed” does not establish independent numerical correctness, output-memory ACK, public PC completion or full Attention completion. Execution, callbacks or scalar operations may have been in flight after the last complete record. Packet/event hashes are not independent numerical evidence.

The previous 0613 frozen prefix summary was read, not reparsed. Under the same counting definitions it had 1,403,851 complete frames, QK 4,039 / PV 9,216 service-completed groups and active token96/head0 PV col0. The current retained prefix is deeper by **990 QK groups, 1,136 PV groups and 362,161 frames**. These are not whole-task throughput, time speedup, a completion percentage, a required larger budget, or isolated causal attribution to the observer. Causal work per token changes and the suffix is still not evidenced.

The parser used 17.011212 CPU s / 16.997218 wall s and 12,058,624-byte peak RSS under its separate small analysis bounds. It made one sequential stream read, computed the digest in that same pass and checked file stability. That digest agrees with the external full artifact inventory. Publication did not rerun the parser or target. Raw event records, tensors and fields are not included; public projections retain counts, source-schedule position and explicit limits only.

## Budget, cleanup and missing acceptance evidence

Original limits remain: one CPU; worker/tree CPU 3,600 s; worker wall 4,200 s; per-process AS 3 GiB; sampled tree RSS 2 GiB; trace 384 MiB; total output 768 MiB; logs 16 MiB; 2,478,403 event cap; 30-second cleanup. Pre/postflight hashing and cleanup keep their original scope outside the worker timer: **this is not a 3,600-second whole-parent aggregate CPU claim**. Per-process hard limits and sampled tree guards are not a kernel-enforced aggregate-tree cap.

Recorded sampled tree RSS high-water and reaped-child maxrss are both 337,203,200 bytes, but are separate measurements: the sampled value is not a continuous peak, and child maxrss is not aggregate-tree RSS. Cleanup recorded no remaining owned identities and no timeout, in 0.016309604 seconds. SIGKILL/kill/reap receipts do not prove whether kernel RLIMIT_CPU or the supervisor's kill arrived first; sampled and reaped CPU both establish budget failure. Cleanup is source/receipt-bound, not raw wait/reap syscall history or a new live PID probe.

All 2,206 source/input/runtime pins passed pre/postflight. The external failure inventory contains **41 artifacts / 171,746,376 bytes**; it is not a retroactive run-native success seal. Normal-load and native-load snapshots survived, including preserved raw namespace/dependency/cache exceptions and their narrow qualifications. These are startup evidence, not full-run runtime acceptance.

Missing: final worker result, completion seal, terminal comparator result, full service-protocol replay, final runtime/policy audit, final capture evidence, installed/cleaned mask acceptance, actual terminal manifest and full public21 terminal. PCs 10–12 publication and PCs 13–20 suffix are not established. Parent source postflight does not replace final worker runtime evidence. Initial sealed oracle activation and terminal-only source policy do not supply a final oracle-policy receipt or per-open/native-syscall history; **no final reference comparison completed**.

No full29 numerical PASS, complete RTL/hardware acceptance, MAC utilization or performance adoption follows. This is a failed case, not an additional passed case for MAC reporting. Native FMA counters and whole-block hardware denominators were not produced; MAC temporal utilization, MAC-active duty and the 90% hardware objective remain unknown/not accepted. Temporary experimental helpers and any unvalidated replacement arithmetic are excluded.

## Public package and reconstruction boundary

The assembly utility reconstructs **16 original-byte files** (all fifteen Python sources plus observer metadata), using fourteen exact public references and the two new source files. The original rope `SOURCE_PINS.json` contains private absolute locators, so it is deliberately omitted and represented by `ROPE_SOURCE_PINS_PROJECTION.json`, retaining its original hash and source identities. This projection is **not** an executable replacement. Private gate/deployment configuration and path-bearing preparation/mock/parser tools are hash-only provenance, not silently rewritten copies.

```sh
python -B candidates/qwen2_full128_identity_failure/assemble_sources.py --repo-root . --output SOURCE_ONLY_FULL128
python -B candidates/qwen2_full128_identity_failure/test_assemble_sources.py
python -B -O candidates/qwen2_full128_identity_failure/test_assemble_sources.py
```

Only inert byte-copy packaging tests execute; no target imports, original tests, native/Matrix/DUT/reference arithmetic or stream parser runs. Output reuse, traversal, symlinks and hash mismatches are rejected. Source reconstruction is not runnable private-experiment reproduction or new admission. `0941_LOGICAL_FILES.json` contains all 2,206 ordered opaque pin records; `0911_LOGICAL_FILES_DELTA.json` exactly reconstructs the old 2,192-record metadata using indices plus ten inline records. Role labels are not physical locators or executable configuration.

Publication adds only source, role-based pins, exact-review/analysis projections and this index. No raw event/tensor/header/weight payload, runtime map/identity, private path, actual approval/capability or consumed-claim body is published. Historical files and statuses are not edited.
