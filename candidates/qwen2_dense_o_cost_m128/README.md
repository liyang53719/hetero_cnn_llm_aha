# Isolated M128 Dense O cost probe

Status: source and cold-control review only. Actual execution requires the
parent's one-use go bound to this exact source manifest and one fresh output.
This package is separate from the frozen266 fullchain candidate and changes
none of its files, budget or input gate.

Every receipt is `ISOLATED_COST_REPLAY_NOT_SAME_CHAIN` with
`numerical_acceptance=false`. It measures one complete original O projection,
not pc0..20, not public completion13, and not hardware cycles/utilization.
No oracle or threshold comparison is performed. A successful cost trace cannot
establish a whole-block runtime bound; resident FFN and Down remain separate
unmeasured paths.

## Exact stimuli and reused code

- att: saved ACKed M128 pc12 output,
  `work/qwen2_live_attention_numeric_m128_bounded_20261014/m128_pv32_bounded_actual_v2/att.f32le`,
  786432 bytes, SHA256
  `d8e888f201396a6125a93c0602aaf3e53bf4700d4298db0795aa8a1355149287`
- wo: original transposed BF16 KxN input,
  `work/qwen2_live_tail_inputs_m128/reconstruct01/inputs/wo.bin`,
  4718592 bytes, SHA256
  `69532da7bcc69b44b0bb627a4c0142f83b6713833d8ec08d6f73926eae80722c`
- ELF: unchanged original strict Matrix/SiLU code,
  SHA256 `a44f4cd7861d1207698bb3dfc89820ded30a44db1cf1c8b9f951019d1edce1fa`

`pins.json` binds the frozen266 fullchain source closure plus its FREEZE,
all underlying driver/owner/adapter source, exact inputs and native/tool hashes.
The original native verifier performs its code-only compiler-version preflight
before the operand audit hook is installed. It does not compile, reset, execute
FMAs or read model operands. The hook is installed before either att or wo is
read; the fresh Matrix reset, service construction and cost arithmetic follow
under the hook. Code/input identities are rehashed afterward.

The original metadata fixture supplies addresses and the original pc13 role
validator checks the isolated job geometry. `ReplayOperands` exposes archived
att only as an explicitly readonly isolated stimulus; it never writes,
ACKs, publishes or marks terminal the original physical att allocation.
wo uses the original physical readonly port. The same real PhysicalMemory
accepts O write command/data/ACK/terminal traffic. There is no public Host,
manual predecessor completion, restored object or forged public job history.

The original `DenseReductionOwner`, `ProfiledMatrixService` and its delegated
`OfficialDenseLibraryAdapter` use the unchanged `down_driver.execute_dense`.
The driver gets the actual Matrix bridge, original sink and its normal owner
tick. No per-tick observer, polling callback, arithmetic patch, shortened N/K,
new compute resource, scalar service or replacement driver is introduced.

## Complete cost boundary

A successful measurement requires all of:
- Original M128,K1536,N1536 geometry; 73728 accepted steps and 301989888 C FMAs
- Ten original N-window groups, 48 actual retired results, one Matrix lease
- 786432 output bytes acknowledged, held final ACK before actual owner terminal
- Actual Matrix done/result/owner-response retirement and release
- Zero remaining owner/Matrix/output debts, unchanged resources
- Zero prefix workspace writes/reads/seeds; no synthesized Down behavior

Fixed resource denominator: 4096 issued cells, five accumulator storage
contexts (81920 bytes), three resident tile storage slots, original A/B banks.
Step counts, useful/executed FMA, native FMA, owner ticks, wall/CPU time and lease
counts are separate. None is reported as hardware utilization.

## Output and fixed budget

The original driver internally forms the O output for its existing checks.
Its sole end-of-run tensor file write is discarded through the exact precreated
`actual_dense.f32le -> /dev/null` path. That path is source-bound to the original
Dense-driver/Path.write_bytes call chain and the full786432-byte final output;
arbitrary tensor writes and reads are rejected. The symlink is removed afterward.
Only metadata, source/input/output hashes and capped original event trace remain.
Original seed/prefix files must be empty for O.

Fixed limits: 60 seconds end-to-end worker, 70 seconds supervisor; one thread;
2GiB child address-space limit and 2GiB sampled process-group RSS; 2MiB total
metadata output, 256KiB combined logs, 1MiB per file; 100ms supervisor sampling.
The 2MiB output allowance covers the 128KiB capped original trace, compact full
source identities, original accepted-group report and failure receipts. There
are no retained tensor payloads. Aggregate RSS/disk/log caps are sampled and
can overshoot between polls; address-space/per-file limits are OS limits.

The prior Q projection had the same73728 wide steps and301989888 C FMAs and
occupied about39.7 seconds, but used the QKV partial profile. This is a reason
for trying a bounded60-second probe, not an O forecast or a full-tail bound.
A timeout is retained as incomplete cost evidence, with actual remaining debts;
OS process cleanup does not execute or prove backend abort/drain. Failure debt
snapshots cover owner/service/physical fields; the original driver local pending,
result, staged and held queues are not exhaustively enumerated. No retry,
automatic extension, or fullchain budget update occurs.

## Cold checks and eventual parent command

Normal and optimized cold suites:

    python -B -m unittest candidates.qwen2_dense_o_cost_m128.test_gate_cold candidates.qwen2_dense_o_cost_m128.test_cold -v
    python -B -O -m unittest candidates.qwen2_dense_o_cost_m128.test_gate_cold candidates.qwen2_dense_o_cost_m128.test_cold -v

The initialized control uses synthetic unread bytes, loads/resets the exact
native resource, constructs original owner/service/sink, verifies the delegated
Official adapter and acquires a real lease. It executes zero owner ticks/FMA and
never reads actual inputs or references. It deliberately keeps that lease
outstanding; no terminal or release is fabricated. All such control evidence
is cold-only and never a successful cost measurement.

After independent source/cold/budget review, only the parent may run once:

    python -B candidates/qwen2_dense_o_cost_m128/launch.py --actual --out work/qwen2_dense_o_cost_m128_20261014/parent_reviewed_o_cost_v1 --reviewed-source-manifest REVIEWED_SOURCE_SHA256

No actual command was executed while preparing this package. No tensors,
weights, raw data or ELF belong in Git. Publishing source/cold metadata does
not approve the command.
