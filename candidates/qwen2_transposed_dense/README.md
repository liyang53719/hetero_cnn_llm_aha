# Transposed Dense software candidate

MODEL ONLY. Original v0 arithmetic and native M128 FAIL remain unchanged. This candidate does not implement RTL, actual iDMA, error propagation or a whole-cycle model.

The mapping uses one logical M128×N32 context across eight existing 16×32 slices. Five real contexts cover N160 and retain each exact FP32 prefix across every K/refill. The production 688 KiB A / 80 KiB B depths are preserved; there is no C snapshot in the implemented model. Down therefore rereads A for ten N160 groups.

## Explicit output paths

No generated source, binary, tensor or report is written into this candidate directory. Existing evidence directories are never overwritten.

```
# No arithmetic execution: addresses, capacities, ports and all 19 owners.
python3 candidates/qwen2_transposed_dense/compare.py \
  --analytic-only --out /tmp/qwen2-transposed-analytic

# One tiny packaging example; no large swap enumeration or official shape.
python3 candidates/qwen2_transposed_dense/compare.py \
  --tiny --out /tmp/qwen2-transposed-tiny

# Explicitly requested bounded suite: 10 cases / 20 mapped runs.
python3 candidates/qwen2_transposed_dense/compare.py \
  --out /tmp/qwen2-transposed-small
```

The analytic receipt has `numeric=null` and `numeric_executed=false`. Neither an analytic receipt nor the tiny check qualifies as the full-chain small-suite prerequisite.

The full-chain entry requires an existing readonly arena and saved rectangular-model baselines. The baseline root must contain `generated/`, `m16/RESULT.json`, `m128/RESULT.json`, their logs and all 15 stage files. No inputs are downloaded.

```
python3 candidates/qwen2_transposed_dense/full_chain.py prepare \
  --out /tmp/qwen2-transposed-full \
  --baseline-root /path/to/existing/qwen2_rectangular_numeric \
  --arena /path/to/existing/readonly_arena.f32le \
  --small-receipt /tmp/qwen2-transposed-small/SUMMARY.json

# Separate, explicit arithmetic actions; not performed by prepare.
python3 candidates/qwen2_transposed_dense/full_chain.py execute \
  --out /tmp/qwen2-transposed-full --tokens 16
python3 candidates/qwen2_transposed_dense/full_chain.py execute \
  --out /tmp/qwen2-transposed-full --tokens 128
```

Preparation verifies input size/SHA, baseline shape, canonical source identity, strict compiler flags, generated source/header/ELF hashes, logs, stage ordering, sizes, finite values and hashes before compiling. Its manifest freezes all inputs, algorithm/source identities and output artifacts. Execution revalidates them. M128 additionally requires this prepared binary's successful M16 receipt, whose 15 stage metadata/hash entries must exactly equal the frozen M16 baseline, followed by file verification. A self-consistent rewritten M16 receipt cannot approve different stage bytes. Each case has a 180-second timeout and no automatic retry. Partial timeout stdout is preserved.

`prepare` changes only Dense and four mechanical capacity declarations/checks/strides in the existing rectangular Attention support. The Attention function is unchanged. Its high-water marks are A 86,016 B and B 81,920 B, fitting the same physical bank depths.

## Evidence identity and packaging boundary

`transposed_dense.inc.cpp` is byte-identical to the separately reviewed work-directory algorithm:

```
5db5c1d071d87a6601200706bb709be486235d6bd8671d3018eb792d42dbce6e
```

`small_tests.inc.cpp` likewise retains SHA `331b4ee38b044766fdbce8bc8b9235bfff53ca356eb762fb6c4d9f95297a82e9`. Both are checked before generation. The reconstructed full-chain C++ matches the historical frozen source SHA `4ce29539e1bd7345d5ccee88c7d70b056ec39bdadae4df416ebb401b9afbdcc1`.

That historical work driver passed M16 and M128, all 15 stages and respectively 663,552 / 5,308,416 FP32 values, against saved v0-equivalent outputs. Its readonly arena SHA was `c34bcef98ca05d3c05087559741152082492b40fa6b74e072a1dec589c964a69`. The paths and preflight checks in this packaged Python entry were refactored afterward. Those historical full runs are **not** described as executions of this packaged driver. Current focused tests execute one tiny C++ example; they do not repeat the ten-case suite, large swap enumeration or official M128.

## Arithmetic and finite/error scope

The model reuses the existing guarded v0 helpers and ordinary C++ compiler recipe: `-O2 -std=c++17 -ffp-contract=off -fno-fast-math`, FE_TONEAREST, FTZ/DAZ disabled, original host probes, and one CPU. Each lane begins at +0, consumes increasing K with strict FP32 FMA, retains its exact FP32 prefix across loads, then adds bias once at the terminal output. It evaluates `fma(weight,activation,prefix)` with swapped finite operands.

The bounded suite covers signed zeros, subnormal/underflow outputs, cancellation, bias ordering, A/B/N/tail boundaries and all eight slices using a synthetic M128/K272/N192 case. Its operand-swap probe checks bits for 5,222,400 directed finite triplets, not the full Cartesian domain. It does not check hardware exception flags. The model rejects nonfinite/invalid BF16 inputs and checks accumulator/output finiteness at the terminal output, **not** per-step flag propagation. Hardware flags, cancellation, output atomicity, error timing and fault drain remain unproved. CPU duration is execution bookkeeping, not hardware performance.

## Bank, route and storage contract

- A: 16×1376×32 B = 704,512 B. For `mt=m//16`, use `bank=(k%16) XOR mt`, `word=(k//16)*8+mt`, `lane=m%16`. Fixed K reads eight different banks, requiring a per-bank address and M-order gather. Full A is retained for K≤2560 in this implementation. K2560 uses 1280 words/bank; the physical maximum K2752 fills 1376.
- B: 16×160×32 B = 81,920 B. Use `linearWord=half*1280+kWithin128*10+nWithin160//16`, `bank=linearWord%16`, `word=linearWord//16`, `lane=nWithin160%16`. Two K128×N160 halves fill the existing banks exactly. An N32 issue or BF16 refill beat accesses two distinct banks. Both halves are exercised serially; no prefetch credit is taken.
- Existing arithmetic storage: five 81,920-B-total FP32 accumulator contexts; eight service metadata slots; two 32,768-B-total service result slots; one 16,384-B finalValue. The retained leaves also have five internal result-register groups totaling another 81,920 B, unchanged. C++ does not simulate those pipeline registers; its array sizes are not a complete hardware payload inventory.
- One FP32 A beat converts to 16 BF16 halfwords and scatters across all 16 A banks at one word/lane. Masked mode needs actual 16-bit SRAM masks and a 16-bank write route. RMW mode uses accept/hold → 16 parallel reads → 16 merged full-word writes, retaining the existing 1R+1W ports. The current DMA's single-bank write selector does not already support either route.
- Both modes explicitly hold 256 converted bits plus an 11-bit word address and lane/phase metadata. RMW consumes the synchronous read response at the guaranteed next write edge; a stalled write would require another explicit 4096-bit hold. First-lane full-word initialization and serial phases avoid uninitialized data and read/write ambiguity. Refill and compute reads do not overlap.
- The service must route two A16 weight groups to four slices each, with M128 activation duplication into B256. This is no additional FMA, but requires muxes, routing/fanout and mode/control. No free area or timing assumption is made.
- Output is gathered directly from the existing finalValue: `physical_row=nWithin32%16`, `physical_col=32*(m//32+4*(nWithin32//16))+m%32`. A beat gathers 16 different physical rows. There is no extra transpose tile.

Metadata/result peak one in the numerical loop proves bounded capacity only, not the five-stage/backpressure protocol. The source leaf's recurrence is five cycles. A three-context group has ideal operand-ready issue span `(K−1)*5+3`; all seven matrices contain 30,198 such recurrence gaps. Refill waits can cover some gaps, so they cannot be blindly added to refill phases.

## Traffic comparison and limits

All seven matrices retain the same 93,585,408 weight bytes, 11,796,480 output bytes and 1,462,272 wide issues. A rises from 13,893,632 B in the old resident mapping to 50,593,792 B: down's ten passes account for the 36,700,160-B increase. C snapshots of 81,788,928 B in each SRAM direction disappear. The old four-phase seed reader alone charged 5,111,808 cycles; this is not a whole-layer timing comparison.

The reused 19-owner/21-command ledger includes separate bias, KV append, Attention, Norm, SiLU and residual transport. Total reads/writes become 164,888,576 / 22,544,384 B, or 2,928,640 64-byte transfers. Conditional on the current serialized shared iDMA adapter, ideal payload service alone bounds useful utilization to 50.1415%. This is not an absolute architectural bound or a whole-cycle prediction.

With burst output writes, N32 produces 92,160 two-beat row segments versus 11,520 sixteen-beat segments in N256. The 8× descriptor ratio does not apply when writes are already single-beat requests. Descriptor fetches, burst legalization, ACKs, scalar/SFU/owner timing, route area and frequency remain unresolved.

The existing analytic-only down alternative uses K2560 outer chunks and a separate 786,432-B DDR prefix region: three boundaries move 2,359,296 B each way. Full-graph DDR would be 150,863,872 B, but a real bounded DDR-to-FP32-seed path, transaction identity and ACK/error lifetimes are absent. It is not executed by this candidate or selected for production. The concrete implemented model retains all five contexts and rereads down A.

Run the focused checks with `python3 -m pytest -q tests/test_qwen2_transposed_dense.py`. No native gates, arithmetic policy or production path are changed.
