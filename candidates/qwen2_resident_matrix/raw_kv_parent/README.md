# Default-off Dense parent raw KV loan exposure

## 中文进度与范围

- 已完成：在现有最终组合的 Down Dense owner 内增加默认关闭的原始 KV 借用接口；严格 source pin 与零 fuzz 三文件组合检查。
- 已完成：原版 DenseReductionOwner 与同一 Banks 的 11 项控制测试，普通 Python 与 -O 各通过 11 项；原始 raw bank 的 8 项模型回归也通过。
- 进行中：父级源码集成审核。
- 待办：本父级补丁的 Scala 编译、RTL 单元验证，以及上层 kernel 的原始 mode-0 Attention K/V 接线。

本批是 owner 侧接口暴露，尚未接入 Attention 消费者。已有 raw_kv 银行级单元测试结果不代表本父级补丁通过编译或 RTL 测试；本批没有运行 Scala、RTL、EDA 或性能测试。

## Composition

`python -m candidates.qwen2_resident_matrix.raw_kv_parent.compose`

Inputs are Git-blob pinned. The three original target sources are composed in order:
owner_prefix → owner_down → tile_ports → window → drain → chisel_policy →
k_window → dense_drain → this integration.patch. The host_workspace, group,
and vector_add patches are pinned and scanned to prove they have no changes to
these three targets. Final preimage and integrated source SHA256 are pinned. The checker also
composes the previously tested raw bank baseline and requires exact equality
of the raw control blocks and raw ABI. This is source comparison only, not a
parent compilation or RTL PASS.
Patch application uses zero fuzz and no source replacement. Existing raw_kv
patch, tests, receipts and all original source patches remain unchanged.

The original bank-level patch cannot be applied after window's constructor
extension. This separate integration patch carries the same raw bank transport
into that final source, then exposes it through DenseOwnerIO and the actual
TransposedDenseDownOwner. `enableRawKv=false` remains the default. There is no
new top, arithmetic path, payload SRAM, external parentDrained input, or global
Matrix-idle requirement. Upper-kernel arbitration and Attention routing remain
future work.

## Exact owner-local debt mapping

The Python adapter reads actual original owner fields; it does not accept an
external boolean claiming that the owner is drained. The corresponding final
Chisel signals are:

| Original Python observation | Final Chisel condition |
|---|---|
| state, error | state===idle, status===0 |
| read_active | !burstOutstanding |
| a_hold, a_rmw_pending | !aHighPending, !banks.activationBusy |
| pending, fifo | operandsEmpty (return reservation and queue); loadState===loadIdle |
| seed_outstanding, seed_state | !seedOutstanding, seedState===seedIdle |
| group_started and not group_done | !(groupStarted && !groupDone) |
| write_state | writeState===writeIdle |
| window_request/window_result | !windowActive, !window.result.valid |
| drain_request/drain_result/drain_expected | !drainActive, !drain.result.valid, !drainReadPending |
| lease | !aLeaseValid |
| tiles pending/response/live tags/poison | tiles.drained, !busy, !leased, !resetRequired |
| drain_poison and held ordinary response | !drainPoison, !io.done.valid |

Historical Python accepted_write/final_value payload references are not valid
bits and are not counted as independent outstanding debt. Chisel also checks
current tile/drain abort and unsolicited response valids. This mapping is
control evidence, not a proof of Python/Chisel cycle equivalence.

Retained A residency must be invalidated through the existing window
invalidateLease input before acquisition. Acquisition stays unready on that
invalidation edge because it observes the old aLeaseValid. Raw acquire.valid
has priority over new ordinary/window/drain/tile offers. Already accepted work
continues to drain while acquisition waits. A held terminal completion blocks
grant until a later edge after retirement. Borrower abort/softReset never
resets the Dense backend or erases its accepted obligations.

Current backend status/tile/drain faults reach raw abort and resetRequired
without feeding back through the owner resetRequired wire. A simultaneous
matching raw ACK retires debt but must not publish a poisoned fill.
Incoming idle/leased DDR, Matrix or seed replies poison parent admission.
They cannot acknowledge a raw transaction. Raw response data/key stay held
until the matching raw ACK; release remains available after retirement.
A borrower protocol reset does not repair a poisoned Dense backend.

## Model limits and resources

ParentLoan owns no payload storage: its raw model and the original owner's
tile model point to the identical original A Banks object. Both original tick
methods reset access counters; the adapter merges the counters after executing
the original owner and rejects simultaneous raw/owner SRAM accesses explicitly.
The caller must use this adapter's admission path; direct bank writes are not
intercepted. Original bank assertions are not strengthened by Python -O.

Chisel adds one sticky parentPoison bit, plus the bank transport's existing
626 explicit bounded response/key/owner/control bits. No extra SRAM or MAC.
The owner-local reset wire is combinational. Counts are source accounting,
not synthesis area, timing, utilization, or hardware-cycle measurements.

Short checks (no Scala/RTL):

```
python -m unittest candidates.qwen2_resident_matrix.raw_kv_parent.test_model
python -O -m unittest candidates.qwen2_resident_matrix.raw_kv_parent.test_model
python -m candidates.qwen2_resident_matrix.raw_kv_parent.compose
```

No workflow changes are included. The dedicated raw-kv-bank-unit workflow
only triggers on its own workflow path, so these six paths do not trigger it.
Other repository workflows retain their existing push behavior; publishing is
coordinated separately after their current runs are terminal.
