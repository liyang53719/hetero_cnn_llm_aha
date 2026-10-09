# BF16 causal GQA owner

This internal owner implements only the attention core between normalized,
RoPE-applied queries plus staged K/V cache and ungated attention output. It adds
no Host opcode and contains no gate, O projection, residual, or FFN. Host cache
identity, length/generation authentication, staging ownership, and whole-block
publication remain separate obligations.

## Interface and allocation contract

`Bf16CausalGqaOwner(maxTokens=128,maxCacheTokens=256)` exposes external
`MatrixStreamPort`, `GdnScalarClient`, and `MemoryRequest/MemoryResponse` clients.
It instantiates no Matrix arithmetic, Scalar/SFU, or DMA service.

- Q: contiguous BF16 `[tokens,8,256]`, token stride4096 bytes, head stride512.
- Cache: BF16 `[2,capacityTokens,512]`, K plane then V plane. Each token occupies
  1024 bytes per plane; V begins at `cacheBase+capacityTokens*1024`.
- Output: contiguous BF16 `[tokens,2048]`, the same Q token/head ordering.
- `1 <= tokens <= 128`, `queryStart+tokens == cacheLength`, and
  `1 <= cacheLength <= capacityTokens <= 256`.
- Every entire allocation, including unused cache capacity, must fit the
  retained transport's `[0,2^56)` aperture, be aligned to64 bytes, and be
  pairwise disjoint. Descriptor end arithmetic widens before addition.
- Each transfer is a complete64-byte beat. Only matching successful output ACKs
  increase `writeBytes`. Only all output ACKs and all Matrix done handshakes
  permit `outputCommitted=true`.

A valid causal descriptor always leaves at least key0 visible. Empty cache or
inconsistent queryStart is rejected before memory activity. The softmax state
also checks that an allowed maximum was found rather than dividing a fully
masked row. Capacity padding is never read or validated as an operand.

## Frozen fixed arithmetic

Pinned upstream boundaries: `config/upstream/qwen3_5_0p8b/modeling_qwen3_5.py`,
`eager_attention_forward` and `Qwen3_5Attention`, lines714–811. The fixed recipe
makes reduction order and exp implementation explicit; it does not claim to
identify the native PyTorch backend's reduction tree or transcendental result.

1. Query head h uses KV head `h/4` (integer floor). QK executes increasing
   d0..255 BF16×BF16 FP32 FMA from+0, terminal BF16 RNE. All live keys execute,
   including future causal-masked keys. Finite FP32 to BF16 overflow is rejected.
2. Multiply the terminal QK by1/16 with shared `MulIeeeRne6`, then BF16 RNE.
   This preserves legal gradual underflow and BF16 rounding to signed zero;
   legacy `Mul1` is unchanged.
3. For each row, consider keys at most `queryStart+localRow`. Find their FP32
   maximum, subtract it in FP32, and reject any unmasked difference<=−80.
   Shared `ExpNegative4` uses range reduction and a degree7 polynomial; its
   saturation outside that domain is unsupported here. Masked exponentials and
   probabilities are exact+0. Sum in increasing-key FP32 order, divide in FP32,
   and convert probabilities once to BF16. Adds/divides retain existing shared
   service error policy.
4. PV executes increasing key0..cacheLength−1 BF16×BF16 FP32 FMA, including
   future zero probabilities, then terminal BF16 RNE. Nonfinite operands,
   intermediate/result errors, and BF16 overflow fail closed.

The independent integer-FMA Python oracle is
`src/heteronpu/qwen35_gqa_fixed_reference.py`. Fixed bit equality (including
signed zero) establishes only this controller/arithmetic contract. A new GQA
stage's native comparison is `UNASSIGNED_DIAGNOSTIC_ONLY` unless an independent
stage gate has already been approved; report its errors without inventing or
inheriting a tolerance. Existing official producer/full-block gates retain their
original source thresholds and failures. The <=−80 rejection identifies a
mathematically legal but currently unsupported input domain.

## Resources and transaction ownership

Queries tile16 with actual final-row count1..16. Keys tile32 with actual final
count1..32. QK uses Matrix opcode0x23, slice mask1, context0; PV uses opcode0x24,
mask255, context0. Only the final reduction step asserts last/finish/emit.
The retained `MatrixResultFifo` must hold result valid and every payload bit
stable under backpressure. Any intervening arbiter must retain this same owner
and payload until result.fire. The owner stages one group of32 FP32 values per
cycle through32 reused BF16 converters. QK needs one beat per active row; PV
needs eight. Only the final staged beat asserts result ready and accepts the
whole result. Terminal done ready opens after collection, or during fault drain.
Early done valid is a protocol fault. No staged score/output is used or written
to DDR until the matching done completes. Shared Matrix arithmetic is not
replicated.

Logical local storage is about49.5 KiB at cache256: Q8 KiB, K16 KiB,
score/exp/prob16 KiB reused in sixteen banks, QK result1 KiB, PV result8 KiB,
and V512 bytes. Q/K/output banks contain eight512-bit words; QK results use
sixteen512-bit words. Score banks have one explicit read port and one write
port. These are asynchronous local Mem buffers; no synchronous SRAM mapping is
claimed. Buffers are independent of total query
count. SRAM inference, placed area, timing, power, and QoR remain unverified.

Each accepted memory request and scalar request is tracked until its response.
Faults suppress commit, drain those outstanding responses, abort/drain an active
Matrix group through its done, and then return one stable completion. An error
locks the owner until reset. Output staging bytes already written may survive;
they are never publication. Reset must also reset/drain shared Matrix, Scalar,
and memory transport. Resetting this owner alone cannot cancel external work.

## Verification scope

The Python tests use small generated data and exact integer arithmetic, with no
weights, captured native intermediates, NPZ payloads, or raw traces in Git.
The Scala harness uses the actual shared Scalar and a controlled Matrix endpoint
that performs software FMA on observed stream operands. That harness verifies
feed, causal/head mapping, ordering, and protocol; it is not real MatrixPipeline
numerical integration. Real MatrixPipeline, retained-iDMA/Host, true cold128 plus
carried128 model acceptance, whole-block atomicity, and synthesis/QoR remain OPEN.

Local verification on2026-10-09 passed35 Python cases and five default16-row
Scala suites: cold2/carried1 from actual append writes; three-row output plus
failed final-write ACK/retry; service/numeric faults;24 descriptor/alias/bounds
rejections; and the first16 query rows of a synthetic128-token descriptor with
pending-cache-read reset. The last case does not execute token127 or prove a
full128-token attention run. The separate Q17/K33 crossing case is present but
its local C++ build was stopped first by the temporary-file budget and then by
a killed compiler process. No numerical outcome was produced for that case;
the kill's cause is unverified.

The test JVM needs `-Xss8m` in this local toolchain. Generated native eval frames
were about2 MiB while the JVM's default thread stack was1 MiB. The same source,
SV, and ELF passed the representative cold/carried test after only increasing
the JVM stack; the earlier SIGSEGV and unsuccessful build receipts are retained.
This is a simulator runtime setting, not a change to arithmetic or tolerances.
