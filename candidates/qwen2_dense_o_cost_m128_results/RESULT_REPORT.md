# M128 isolated O cost result

One original cost run completed on 2026-10-14 at 15:24:47 UTC. It reused the saved,
sealed pc12 `att` bytes and original `wo` with fresh Matrix state. This was an
isolated readonly replay through the unchanged Dense owner, service, adapter and
driver. Numerical acceptance, same-chain acceptance and fullblock acceptance are
all false; no oracle comparison was performed. Oracle access is denied by the
closed source gate; the original result does not include an audit read counter,
so zero reads is a source-path inference, not a recorded counter. Fullchain source-only package
`0f7dea98` still has a null budget pending the remaining representative paths.

## Observed cost

- Parent end-to-end: 16.059408704 seconds
- Worker end-to-end: 15.796599202 wall / 15.782677164 CPU seconds
- O stage: 14.970418601 wall / 14.961518041 CPU seconds
- Original driver only: 14.964854578 seconds
- Worker peak RSS: 86144 KiB; separately sampled process-group peak: 87322624 bytes

These boundaries differ deliberately. There is no claim that O improved over the
previous Q projection: Q used another reduction/partial profile. The 73728-step
O measurement alone is insufficient to bound resident FFN, SiLU and seeded Down.

## Actual service and resource accounting

The run accepted 73728 steps, 10 groups and 48 result packets, executing
301989888 C++ FMA calls. Useful and executed FMA counts both equal 301989888;
the fixed 4096-cell step-opportunity count is also 301989888. This is work/fill
accounting, not a hardware busy or throughput measurement. The same five
accumulator storage contexts (81920 bytes), three resident storage slots and
original A/B banks remain. Storage contexts are not separate issue engines.

There were 86016 input-read descriptors, 12288 output 64-byte beats and 6912
command/ACK transactions covering exactly 786432 output bytes. Final ACK was at
functional tick 223460; terminal followed at 223461, after five held-ACK ticks.
One Matrix lease was acquired, responded and released. All recorded owner,
Matrix, tile and physical output debts are zero. No Down prefix/seed or SiLU
work was executed. Public Host completion13 was not executed, and the archived
att allocation was never fabricated as physically published.

## Identity and limits

All 275 frozen source hashes and both input hashes match before/after. The native
code artifact was verified and explicitly reset in a new process; no older
numeric state or acceptance was inherited. The original att run's launcher
FAILED status remains intact; its independently audited sealed bytes alone are
used as isolated cost input.

The source README's phrase “2MiB total metadata” is clarified here and in the
pre-execution independent review: the worker directory is capped at 2MiB, the
separate supervisor receipt at 1MiB, and combined logs at 256KiB. RSS, disk and
logs are sampled every 100ms and can overshoot between polls; the worker address-space and
per-file limits are OS-enforced. The separate launcher receipt limit is checked
by serialization length in save(). Worker/outer wall limits were 60/70 seconds;
there was no retry. Actual worker metadata is 96936 bytes, logs 131 bytes.

No tensor artifact is retained: the original driver's final file write alone
was discarded via the exact source-bound /dev/null path, after real physical
O output coverage, hash and ACK checks. This affects file persistence only;
it is disclosed rather than compared with a disk-writing timing as a speedup.

The frozen FREEZE/README retain their source-preparation-time status. This
separate result records the subsequent execution. Independent final-result
review is complete: VERIFIED_COST_ONLY_O_COMPLETE, receipt SHA256
`a2665462001276c2ac7f128719f125bd58244400bb1dfe476da275335b597055`.
The reviewer rehashed the original records and performed no arithmetic replay. Nothing here establishes
hardware cycles, hardware utilization, target-DDR timing or a whole-block bound.
