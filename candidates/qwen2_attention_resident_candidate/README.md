# Bounded resident KV supply for the actual live PV32 owner

Cold-by-default, independent software candidate. The owner subclasses the actual
OfficialPV32AttentionOwner and inherits _attention, _matrix_step, _pv32_step and
_op unchanged. Only raw FP32-container KV delivery changes. The original QK
lane fold, two BF16 boundaries, Scalar polynomial/normalization, per-key PV FMA
order, PV32 borrowed reply and two-output-ACK retirement remain intact.

The caller supplies one exclusive SharedAScratch and immutable allocation and
producer-generation identity. The capacity models existing A: 16 banks times
1376 words times 32 bytes (688 KiB). Fixed K/V reservations are 128 KiB each;
4096 valid bits cost an additional 512 bytes. A 64-byte packet maps to distinct
banks 2*(line%8), 2*(line%8)+1 at word line//8. Each access uses one 256-bit port
on each bank. It has one outstanding request, at least one response edge, a
stable held 64-byte response, and explicit consume ACK. No per-hit arithmetic,
FP32/BF16 conversion, dictionary cache or extra Matrix is introduced.

Misses follow the original physical MemoryRequest/MemoryResponse checks. Only
accepted raw response bits enter a local fill request; valid is committed after
the local write ACK. Hits use explicit local requests and responses. A lease
binds addresses, extents, job tag, token count, output span, allocation identity,
producer generations and a fresh cache epoch. No line survives lease release.
Write/generation notifications revoke the lease; accepted memory, local and
Matrix obligations drain before terminal and reuse. Request validation precedes
all bank mutation, including direct malformed request injection.

This new local route and global Dense/Tile/Attention A arbiter are NOT connected
Chisel interfaces. Existing GQA and rectangular candidates provide capacity and
lifecycle precedents only. Their different arithmetic and PASS results are not
inherited. In a full-chain integration, existing Dense/window/tile leases and
pending memory must first drain, and a single shared bank clock/arbiter must
exclude every other A user for the entire lease. The present small harness owns
A exclusively and exercises denial of a conflicting external lease. It does not
claim that production integration or M128 acceptance exists.

Run cold tests with `python -m unittest
candidates.qwen2_attention_resident_candidate.test_cold`. The optional
check_small --execute --out WORKPATH uses synthetic M1/M2 only, unchanged actual
Matrix/Scalar services, original read-only observation fields, ACK-only output,
and bounded failure injections. The launcher must impose a 75-second wall
limit; the process imposes CPU60s/AS2GiB and checks total output below32MiB.
Detailed artifacts stay in work. Outputs, intermediate words and tensor hashes
are not publication payloads. All software edges are protocol events, never
hardware-cycle or utilization estimates. Caching cannot repair prior original
numerical-gate failures or the one-Matrix issue geometry limitation.

## 空 owner 租约修复与小步验证（2026-10-16）

- 已完成：resident acquire 与 external reserve 在任何状态修改前拒绝 None owner。
  None 是未占用哨兵；此前允许它会让第二个客户端重复取得同一 A scratch。
  非 None 的 falsey owner 仍按对象身份正常工作。
- 已完成：7 项合成回归在普通与 -O 模式均通过，覆盖双入口拒绝且状态不变、
  客户端互斥、64B fill/ACK/read、held response、撤销后排空与释放后重获。
- 待办：完整模型、共享 A 集成与 Chisel/RTL 验证未在本轮运行；不继承其通过结论。
  本次不改变算术、bank 映射、存储容量、吞吐声明或硬件周期口径。

精确命令（仓库根目录）：

```sh
python -B -m unittest candidates.qwen2_attention_resident_candidate.test_scratch_ownership
python -B -O -m unittest candidates.qwen2_attention_resident_candidate.test_scratch_ownership
```
