# Default-off raw 64-byte KV bank-port candidate

This is a small bank-level candidate, not an integrated Attention owner or a
completed hardware datapath. Existing source, frozen patches and receipts are
unchanged. Apply `raw_kv_port.patch` to the `TransposedDownDenseBanks` source
**after** `transposed_down/owner_down.patch` and `ffn_tiles/tile_ports.patch`.
The new `enableRawKv` parameter defaults to false. No current owner enables it.

## Contract

- Reuses the existing 16 × 1376 × 256-bit A allocation. No new SRAM or MAC.
- Lines 0..4095 map to banks `2*(line % 8)` and `2*(line % 8)+1`, word
  `line // 8`. Low 256 raw bits use the even bank. Last line uses banks 14/15,
  word 511. No finite-value check or conversion: NaN/Inf encodings survive.
- A nonzero 32-bit owner acquires only when local Dense/Tile work and leases
  are quiet and the parent asserts `parentDrained`. Parent must derive this
  from actual Dense/DMA/matrix/seed/response obligations. This patch does not
  connect that parent signal or perform producer/publication validation.
- Lease excludes Dense reads/loads, Tile admission and A clears; B weight
  writes are also suppressed. Existing accepted local work blocks acquisition.
- Exactly one accepted read/write. Write updates two existing banks on its
  acceptance edge; read uses their existing synchronous read outputs. The
  reserved next edge captures one response. No request/ACK turnover bypass.
- Response is Valid-only and held unchanged until a separate Decoupled ACK
  exactly matches owner, tag, line and write/read kind. Tags must be nonzero.
  The 13-bit line field rejects 4096..8191 rather than aliasing. Encoded RTL
  fields cannot represent Python null/float/bool aliases; the model rejects
  noncanonical host values explicitly.
- Cache validity is NOT stored here. The cache may publish a fill only after
  matching ACK and with `resetRequired` false, including the current abort or
  softReset inputs. An aborted fill may have written SRAM but is not valid.
  Accepted debt and owner survive abort/protocol reset until response ACK and
  a later release. Poison then requires softReset while unleased and drained.
- `softReset` is a protocol request. Actual global/module reset is cold reset
  and needs system-level quiescence; this candidate does not retain state
  across a power/reset-domain loss. Parent owns generation/tag freshness.

## Bounded state and model limitations

Enabled raw control adds one 512-bit response register, a 78-bit key, a 32-bit
owner and four control bits (626 explicit register bits). SRAM output wiring
is combinational, not a new payload array. No request payload hold is needed
because writes commit on acceptance. No extra cache-valid array is allocated.
Physical implementation/resource accounting remains unverified.

`model.py` takes the original `transposed_down.model.Banks` object; it never
allocates another bank array. Its pending response represents the synchronous
SRAM output reservation. `tick` controls the model edge and returns admission
permissions; it does not intercept arbitrary direct callers of Banks or wire
an actual Dense owner. The model is an executable specification, not RTL.
Original Banks uses asserts for duplicate physical accesses. The tests also
explicitly inspect access dictionaries; optimized Python does not prove those
original assert-based checks are active.

## Short checks

From repository root:

    python -m unittest candidates.qwen2_resident_matrix.raw_kv.test_model -v
    python candidates/qwen2_resident_matrix/raw_kv/check_source.py

The model checks all 4096 M128-capacity lines with raw writes/reads, untouched
higher words, exact two-bank access sets, boundaries, invalid/foreign keys,
single outstanding request, held responses, early/mismatched ACK and release,
parent obligation and port conflicts, fill publication, abort and softReset.
The source gate verifies pinned Git blobs, zero-fuzz composition, unchanged
SRAM declaration counts and single per-bank read/write call sites. Those are
text/source checks, not proof of synthesizability or behavioral equivalence.

Bounded Scala compilation, four CHIRRTL configurations and three bank-only
Verilator ScalaTests passed at commit `938bbdbe` (`PASS_BANK_UNIT_ONLY`).
See the verified evidence in [UNIT_PLAN.md](UNIT_PLAN.md). Full-block tests,
owner integration and EDA remain unverified. The frozen 24,640-cycle stimulus
count is unit-test coverage, not workload latency or throughput. This bank-only
unit has no MAC; MAC utilization and duty are N/A.

## 中文范围说明

本批次仅新增默认关闭的原始 64B KV 借用端口候选补丁、软件行为模型、
短测试和源码组合检查。它复用原有 16×1376×256-bit A SRAM；不新增 SRAM、
MAC 或缓存数据副本。新增控制/返回寄存器为 512-bit 数据、78-bit key、
32-bit owner 和 4 个状态位，共 626 bit（源码级统计，不代表综合资源报告）。
有效位由上层缓存管理，只能在正确 ACK 且没有 abort/reset poison 时发布。

尚未接入真实 Dense/Attention owner 或 kernel；parentDrained 仍需上层根据
真实 DMA、matrix、seed、response 等未完成事务产生。有界 Scala 编译、
四种 CHIRRTL 配置和三个 Verilator bank-only 用例已通过，范围仅为
`PASS_BANK_UNIT_ONLY`，证据见 [UNIT_PLAN.md](UNIT_PLAN.md)。完整 block、
真实 owner 集成和 EDA 尚未验证；24,640 个冻结向量周期不是任务延迟或
吞吐测量。bank-only 单元不含 MAC，MAC 利用率与 duty 均为 N/A。
协议 softReset 保留已接受事务；冷复位不在此保证内。
原有源文件、冻结补丁和收据均未修改。

## 中文任务清单

- [x] 已完成：默认关闭的 raw64B bank-port 候选补丁和行为模型。
- [x] 已完成：8 项短模型测试，普通/`-O` 两种模式均通过；两种模式源码组合检查通过。
- [x] 已完成：4096 行容量映射、原始位保真、背压、ACK、排他、drain、abort/reset 和提前释放检查。
- [x] 已完成：有界 Scala 编译、四种 CHIRRTL SRAM 审计和三个 Verilator bank-only 用例通过。
- [ ] 待办：接入真实 owner/Attention M128 路径，验证真实 parentDrained 和缓存发布边界。
- [x] 已完成：24,640 个冻结模型周期、4096 行容量的 bank-only RTL 对照验证；不是完整 M128 Attention 验收。
- [ ] 待办：真实 owner 集成后再评估性能；当前 MAC 利用率/duty 为 N/A，无吞吐结论。
