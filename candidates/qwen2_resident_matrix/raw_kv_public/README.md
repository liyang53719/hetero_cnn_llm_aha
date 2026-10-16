# Public PV16 KV transport preparation

This is a default-off, source-bound software-model hook. No full public job,
native arithmetic, Chisel or RTL run has been executed for this change.

## Executing lineage

The existing PV16 path is
`dense_block_reduce.check_public_numeric.run` → `ReducedPublicExecution` →
`OfficialPublicExecution` → `PublicExecution`, followed by the existing
`ffn_public.fullgraph_execution.execute_public_suffix`. Historical numerical
receipts belong to that unmodified path, not to this prepared KV extension.
This does not select the separately prepared PV32 runner.
The historical receipt is
`reports/execution/QWEN2_DENSE_BLOCK_REDUCTION_20261012/M128_RESULT.json`,
source commit `38b943cdf6a0e2d642a1aef07b30e6d23e3ceed8`, receipt Git blob
`c28522da9cb0bcae46fe36c8a5fa1eb373fc6b7d`. Its status is
`PASS_REDUCED_BF16_OBSERVED_OFFICIAL_GATES` with no failed assigned official
stages. That historical result is not inherited by this extension.
The receipt was published after its matching source commit; the pin is its
actual receipt blob, not a claim that the receipt existed at that source ref.

`prepare.py` checks the original source pins and the existing 52-input PV16
numeric closure, then applies `public_execution.patch` to two real source
files in a fresh output tree. It checks exact generated hashes, unchanged
unrelated methods, and the unchanged physical-memory IO loop and its accepted
terminal/report. It does not import or run a numerical entrypoint.

## Optional routing

- `execute_public_suffix(..., enable_raw_kv=False)` and
  `execute_attention_owner(..., enable_raw_kv=False)` retain the original path
  by default. The flag must be a canonical boolean.
- The existing `check_public_numeric.run(..., wall_budget=900)` still calls
  `execute_public_suffix` without this flag. Its runner/CLI therefore remains
  on the original route. This batch prepares the optional coupling hook only;
  a top-level entry switch and its source-freeze/launch policy remain pending.
- The opted-in driver binds `PublicKvTransport` after original Host dispatch,
  using `ParentLoan(owner=x.owner, enabled=True)`. There is no second Dense
  owner or SRAM allocation on this path.
- The binder requires the concrete transport and exact original
  `OfficialAttentionOwner`, `ParentLoan` and `DenseReductionOwner` types. It
  preserves the existing Official/Reduced constructor checks and verifies
  the previously validated job metadata when present.
- The original arithmetic owner, Matrix service, scalar service, decoded job,
  Dense owner and SRAM identities remain attached. Identity checks repeat
  before each optional Attention edge.
- The transport supplies the external memory-channel edges to the unchanged
  physical driver. Only K/V read metadata is retained; data is read from the
  same physical memory and stored in the existing raw A banks.
- This driver API does not advertise `memory_response_ready`. The original
  PhysicalMemory driver offers a response and retires it only on the returned
  `memory_response_fire`; a K/V fill fires only when the raw bank accepts it.
  It is not a general Decoupled interface or an RTL port specification.
- `ParentLoan` ticks the actual Dense owner once inside each transport edge.
  The optional public branch suppresses the former second idle Dense tick and
  checks a clock delta of exactly one. Ordinary Dense/MLP edges retain their
  original implementation.
- Host result readiness remains authoritative. The transport withholds the
  Attention terminal until external memory, raw response/ACK and loan release
  obligations retire. The existing final-write-ACK hold, Matrix release,
  physical terminal and public completion/publication checks remain intact.
- A completed transport may remain attached for identity/audit checks while
  later Dense jobs run. It does not receive those Dense edges or touch SRAM.

## Cold evidence only

The 16 cold tests pass normally and with `python -O`. They exercise actual
Dense owner transactions with opaque Matrix control tokens, Dense → Attention
→ Dense bank reuse, and the original `PublicExecution` / Frontend / HostControl
path with an exact `OfficialAttentionOwner` through its first K request, stopping
before arithmetic. Each optional edge ticks the actual parent exactly once.

A separate, explicitly scripted CONTROL_ONLY consumer exercises the actual Host
completion fence through 1,536 output ACKs, a stalled raw ACK, loan release and
three held completion edges. It is not admitted through the exact-type public
binder and is not numerical Attention evidence. Negative tests cover foreign
responses, held-terminal faults, atomic binding rejection, source/patch drift,
and changes to the original physical loop and ordinary Dense edge.

The original Official/Reduced constructors and complete numerical path have not
been executed by these tests. Their source/type/policy checks are preserved by
composition checks, not inferred from native execution. The historical receipt
has no failed assigned official stages, but its auxiliary reference failures
and incomplete full-29-node acceptance remain unchanged.

## 当前状态

- 已完成：默认关闭的两处原始源码补丁、固定来源及生成哈希、同一 Dense
  owner/Bank 身份与每边沿一次 tick 检查；16 项冷测试在普通及 -O 模式通过。
- 已完成：真实 Public Host 首个 K 请求控制链、单独标注的 Host 完成债务围栏
  测试，以及零模糊源码组合；不包含原生算术执行。
- 进行中：本批固定源码与独立审查。
- 待完成：原入口可选开关及完整数值路径验证；原 Official/Reduced 构造器、
  完整数值链、Chisel 和 RTL 尚未执行，不继承历史 M128 PASS 或宣称性能收益。

Test commands:

```sh
python -m unittest candidates.qwen2_resident_matrix.raw_kv_public.test_model
python -O -m unittest candidates.qwen2_resident_matrix.raw_kv_public.test_model
```

Preparation command:

```sh
python -m candidates.qwen2_resident_matrix.raw_kv_public.prepare
```
