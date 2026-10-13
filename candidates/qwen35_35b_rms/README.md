# H2048 input RMS component reference

This directory adds a model-only RMS component reference for Qwen3.5-35B-A3B.
It does not claim a complete native block forward, Chisel/RTL execution,
hardware latency, or a complete runtime dependency source closure.

## Authority and execution

`reference.py` verifies the original modeling file and configuration hashes,
then compiles the **entire unchanged** `Qwen3_5MoeRMSNorm` class AST at original
lines 878–895. The supplied external namespace is `torch` and `torch.nn`
(plus ordinary Python builtins and a module name). No surrounding model is
imported or initialized. Original forward code and line numbers are preserved.
The installed runtime's Transformers package belongs to an earlier task; it
is explicitly not the authority for the 35B class.

- Transformers revision: `42ca97014c85d71a88ad60d55f08cb9fb4d26e2c`
- Model revision: `62704185bd97ad488cfc404e7caea797396b74dc`
- Original source SHA256: `ea77a3979cb659dd04dc1f6a1cd7d3df53ddc5759e40eb0d5e98846e95b39d30`
- Whole class SHA256: `106cb15a68082e904cf98595202659710df28f2c059ace123246369914436073`

The diagnostic checks actual Torch 2.10.0+cpu, NumPy 2.3.5, DEFAULT dispatch,
one CPU, both Torch thread counts of one, wrapper/receipt hashes, and actual
Torch CPU, Torch extension and NumPy extension binary hashes. These binary
pins are observations of the recovered verified runtime, not new upstream
source-build provenance. The wrapper alone leaves inter-op threads at nine;
the diagnostic pins that count to one before execution.

`component(hidden, weight, tokens)` accepts complete original BF16 bytes and
executes shape `[1,M,2048]`. Its trace observes the real dispatched outputs of
the original forward. `sum_auxiliary` is an explicitly separate `torch.sum`
diagnostic; the original class uses `mean`, whose actual result is captured.
`runtime_identity()` is the required runtime gate for accepting an execution;
the CLI calls it before any case. Returned arrays are host-only observations.

`payload_case(directory, manifest_sha256, token_ids)` reads an already acquired
local payload through its verification loader, using the independently retained
manifest digest. It selects original embedding row IDs without tokenizer or
remapping and passes original norm weights unchanged. No acquisition occurs.

## General formula and observed result

Every square, addition, multiply, sqrt, and divide is rounded to FP32. For each
lane 0..7, each residue 0..3, each block 0..3, and each term 0..15, the input
index is `512*block + 32*term + 8*residue + lane`. Each block starts at +0 and
adds its 16 squares in ascending term order. Each residue adds four block
sums from +0, each lane adds four residues from +0, and total adds eight lanes
from +0. The subsequent graph is:

1. `mean = sum * FP32(1/2048)`
2. `variance = mean + FP32(1e-6)`
3. `inverse = FP32(1) / sqrt(variance)`
4. `scaled = BF16_input.float * inverse`
5. `gamma = FP32(1) + BF16_weight.float`
6. `weighted = scaled * gamma`, then BF16 round-to-nearest-even

The formula is independent of observed outputs. It contains no correction for
a particular cell. It models numerical nodes, not the shared scalar service's
legacy exception flags; owner tests must separately preserve those faults.

The bounded diagnostic compared full M16 and M128 random tensors, 16 edge
rows at M16/M128, and actual embedding rows 0..15 / 0..127 with actual input
norm weights. All compared FP32 nodes and final BF16 words matched exactly.
Isolated same-variance sqrt/div versus native rsqrt and final materialization
also matched. The legacy ascending reduction control showed sum differences.
This finite set is evidence for the general four-block rule, not a proof for
all finite inputs or all Torch builds. The original per-node max/mean limits
remain 0.03125 / 0.005. No relaxed threshold is introduced.

## Bounded-storage schedule implemented by the software owner

Preserve exactly three 1024-entry BF16 stores: input, weight, output, each
2048 bytes. During reduction, reinterpret only the first 64 output entries
as 32 FP32 accumulated residue sums (128 bytes). No FP32 row array is needed.
Scalar scratch is one block sum, one residue value, lane/total accumulation,
mean/variance/root/inverse and arithmetic operands; these are reused scalars.

1. Read input elements 0..1023 into the existing input store (32 × 64B).
   Process blocks 0 and 1. For each block, for each lane/residue, sum its
   16 squares in ascending term order. Add that completed block sum to the
   corresponding output-store FP32 residue entry. A block sum and running
   residue are distinct values: do not keep directly adding later squares
   into the previous block's residue, since that changes rounding order.
2. Read input elements 1024..2047 into the same store (32 × 64B). Process
   blocks 2 and 3 in the same manner, retaining the 32 FP32 residue entries.
   Independent lane/residue execution may be interleaved; each residue must
   add blocks in order 0,1,2,3.
3. Read the 32 partials, summing residues in ascending order within each
   lane, then lanes in ascending order. Calculate mean and inverse. All
   partials are dead now, so the output store can hold BF16 writeback.
4. The simple address-ascending schedule rereads input chunk 0 and reads its
   weight chunk, computes and writes its 1024 BF16 outputs, then rereads
   input chunk 1 and reads its weight chunk, computes and writes those.
   Finish only after all write acknowledgements and the existing publication
   fence. No whole H2048 input/weight/output or FP32 array is retained.

Per token for this canonical schedule, excluding transport metadata:

| Resource | Bytes | 64B DDR beats |
|---|---:|---:|
| DDR input reads (reduction + reread) | 8192 | 128 |
| DDR weight reads | 4096 | 64 |
| DDR output writes | 4096 | 64 |
| Input-store writes / reads | 8192 / 8192 | n/a |
| Weight-store writes / reads | 4096 / 4096 | n/a |
| Output-store BF16 writes / reads | 4096 / 4096 | n/a |
| Partial-store FP32 writes / reads | 512 / 512 | n/a |

Partial-store counts assume each block writes 32 accumulated FP32 entries;
block 0 takes a scalar +0, so reads comprise blocks 1..3 (96 entries) plus
the final 32-entry reduction. Explicit zero initialization instead adds 128B
of writes and 128B of block-0 reads. A physical implementation using paired
BF16 words needs two such word accesses per FP32 entry; no extra port or
dual-width SRAM is implied. These are logical traffic counts, not cycles.

Relative to an unbounded full-row design caching the entire weight once for
M tokens, canonical DDR reads increase from `4096*(M+1)` to `12288*M` bytes,
an extra `8192*M-4096`; output writes stay `4096*M`. M16 totals are 196608B
read / 65536B write; M128 totals are 1572864B read / 524288B write.

An optional lower-traffic schedule consumes retained input chunk 1 first,
then rereads chunk 0, allowing out-of-order destination chunk writes. That
saves one 2048B input read per token (160 read beats rather than 192), and
2048B of input-store writes. It still needs both weight chunks. The canonical
schedule above is implemented in owner.py; the optional reorder is not enabled.

Arithmetic per token is 6145 FP32 multiplications (2048 squares, one mean,
4096 output multiplies), 4265 additions (2048 block terms, 128 block-to-residue,
32 residue-to-lane, eight lane-to-total, one epsilon, 2048 gamma), one sqrt,
one divide, and 2048 BF16 conversions. Redundant +0 operations are counted;
any elision needs its own equivalence/fault-policy justification.

## Reproduce

Cold source/formula tests require only NumPy, no Torch or work cache. From
the repository root:

```sh
PYTHONPATH=src:. python -m unittest candidates.qwen35_35b_rms.test_reference -v
```

The optional official-component diagnostic uses the existing recovered runtime:

```sh
work/qwen35_runtime_20261012_recovered/python.sh -m candidates.qwen35_35b_rms.diagnose --output work/a_fresh_rms_component_report
```

For already acquired real data, add `--payload PATH --manifest-sha256 DIGEST`.
Use a fresh output directory. The diagnostic applies hard 55-second CPU and
wall budgets; the initial six-case actual+synthetic run used 2.46 CPU seconds.
Execution reports belong in `work/`, not in a source-derived acceptance claim.

The memory-fed owner reuses the original RMS admission, transport, scalar and
publication implementation. Its M1 tests additionally cover scratch overlay,
actual request ordering, faults, abort/reset and immutable observation.
The real M16→M128 gate uses one owner/Scalar/TypedMemory instance and compares
only after actual output ACK and terminal acceptance; original outputs remain
intact across the next job. It does not implement the production Chisel path.

```sh
PYTHONPATH=src:. python -m unittest candidates.qwen35_35b_rms.test_owner -v
work/qwen35_runtime_20261012_recovered/python.sh -m candidates.qwen35_35b_rms.run_owner --payload work/qwen35_35b_initial_payload_20261013 --manifest-sha256 RETAINED_MANIFEST_SHA256 --output work/a_fresh_typed_rms_gate
```

The retained manifest SHA must come from the independently verified acquisition;
it is not accepted from a rewritten payload manifest itself. Raw tensor evidence
from this command stays under ignored work/. Software model ticks and host runtime
are not hardware cycles; Matrix utilization, busy/duty, stalls and overlap remain
unknown until the physical schedule and timeline are measured.
