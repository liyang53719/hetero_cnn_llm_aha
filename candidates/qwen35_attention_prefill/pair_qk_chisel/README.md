# Opt-in pair-high-first QK source overlay

Status: **candidate source plus bounded static/symbolic checks only**.
Scala frontend, Chisel elaboration, RTL simulation, and numerical execution of
this overlay are **NOT RUN**. There is no hardware or end-to-end acceptance.

`Bf16CausalGqaOwner.scala` is a replacement source overlay for
`chisel/continuous_prefill/src/main/scala/heteronpu/continuous/Bf16CausalGqaOwner.scala`.
The production file has not been edited. Select one copy in an isolated source
set; never compile both copies together. This is the same owner and the same
`Bf16CausalGqaJob`, result, memory, Matrix stream, and scalar interfaces.

## Explicit option and exact change

The only new constructor parameter is trailing and defaults off:
`enableQkPairHighFirst: Boolean = false`. An isolated integration can explicitly
instantiate `new Bf16CausalGqaOwner(enableQkPairHighFirst = true)` using this
replacement. There is no runtime policy field, private opcode, automatic value
selection, or production Host wiring in this deliverable. The option applies
to QK operand traversal for every job handled by that elaborated owner.

The original eight-bit `dimension` register remains the accepted-step index
0,1,...,255. One combinational Scala-selected alias drives the existing Q/K
packed-buffer read addresses:

- Off: `qkDimension = dimension`, recovering the old read expressions.
- On: `qkDimension = dimension ^ 1`, selecting 1,0,3,2,...,255,254.

Both Q and K use that same address. Its bits 7:5 still select the original
512-bit word and bits 4:0 the BF16 lane. Adjacent pairs cannot cross a 32-lane
word boundary, so buffer banking, capacity, writes, and all row/column masks
are unchanged. There are still 256 accepted Matrix QK steps: each step uses
the existing FP32 FMA path, followed by the original terminal BF16 RNE. The
change does not create a pair-sum operation or an additional rounding point.

`clear` remains tied to logical step 0; `last`, `finish`, and `emit` remain tied
to logical step 255. Thus the first operand dimension is 1 with `clear=true`,
and the final operand dimension is 254 with terminal flags true. The counter
advances only on `io.matrix.step.fire`. A held step keeps its counter, address,
operands, and flags stable under the modeled lack of accepted progress.

PV remains increasing key 0 through cacheLength-1, using the original
probability and V sources. QK remains opcode 0x23 / slice 0; PV remains opcode
0x24 / all eight slices. Query head h still maps to KV head floor(h/4). All
result row/beat selection, scalar/softmax work, memory addresses, acknowledgment
fences, completion, error/drain, and reset-required behavior are byte-identical
to the baseline after the permitted source substitutions are reversed.

No register, memory/buffer, enum/state, FP unit, or owner/module instance is
added. The source delta is the constructor option, documentation, one
combinational alias, and its use at two read sites. This is a source inventory
claim. Synthesized area, wiring, latency, banking, and timing are unmeasured.

## Bounded verification

From the repository root:

```sh
python3 -B candidates/qwen35_attention_prefill/pair_qk_chisel/check_overlay.py
python3 -B -m unittest candidates.qwen35_attention_prefill.pair_qk_chisel.test_overlay -v
```

The existing candidate test discovery can find `test_overlay.py`. Nine checks:

1. Pin the production SHA256 and recover its exact bytes by reversing only the
   explicitly allowed source edits, including default-off address substitution.
2. Reject representative unapproved terminal, key, opcode, and result changes.
3. Compare all bundle/storage/state declarations and non-QK logic exactly.
4. Bind the alias and both Q/K read sites to the source; check terminal controls.
5. Exhaust all 256 pair mappings, default mappings, packed banks, 16 Q rows,
   and 32 K columns with distinct symbolic BF16 payload markers.
6. Cover every partial row/column extent and all 16 result rows × 8 beats × 32
   lanes; retain the original query-to-KV head grouping.
7. Mock accepted progress with no stalls, three stalls at each step, and varied
   stalls. Check held packets, all accepted dimensions, identical control
   traces, and transition to resultQk only on accepted logical step 255.
8. Check PV source selection and ascending key/terminal behavior for every
   cache length 1..256, under both constructor choices and mocked holds.
9. Compare the complete symbolic 256-FMA association with an independent pair
   enumeration. No floating-point arithmetic is executed by these checks.

`source_audit.json` records the bounded check result. These tests are source
checks plus a Python symbolic/mock model, not a Scala interpreter, cycle-level
simulation, proof of hardware handshake behavior, or arithmetic acceptance.

Pinned baseline SHA256:
`d4c1047d275fa0b38d9498fdf6c22018f52138b21a49e55866661a4d4e635cd9`.

## Numerical motivation and scope

The earlier same-input diagnostic is recorded in
`work/l3_matrix_qk_pair_diagnostic_20261012/SUMMARY.json` and `metadata.json`.
It executed generic numerical recipes independently of this Scala overlay and
preserved the original ascending failure. It reports:

| Full QK result | Pair-high-first BF16 mismatches | Ascending BF16 mismatches |
| --- | ---: | ---: |
| cold128, 8 × 128 × 128 (131,072 cells) | 0 | 1 |
| carried128, 8 × 128 × 256 (262,144 cells) | 0 | 2 |

The fixed official replay was Torch 2.10.0+cpu, oneDNN 3.7.1,
`brg_matmul:avx512_core_bf16`; original operator thresholds remained
max_abs=0.03125 and mean_abs=0.005. This full-matrix comparison includes masked
future cells. On active causal cells, ascending differs in 0 cold cells and
1 carried cell; pair-high-first differs in none.

That diagnostic verified identical Q/K inputs, normal-or-zero source operands,
and no subnormal pair-order FP32 intermediate accumulators for these cases.
Its strict FP32 RNE FMA recipe is evidence in that observed domain only. This
routing overlay adds no FTZ/DAZ implementation or input-domain restriction and
does not establish universal ISA/backend equivalence, subnormal behavior, or
parity for other backend versions, shapes, inputs, or reduction schedules.
The existing admission and numerical-error rules remain unchanged.

The recorded variant metadata SHA256 is
`89e6312820fa9b0eb7de23e6a65a5011936086359222a3f0a976be6dcea0d7d3`;
its numerical variant ELF SHA256 is
`6da2cdb028c57d0a43f0a88660c1a87396a9ee381c2e7ec2d4e804571221c630`.
These identify inherited diagnostic evidence, not a frontend or RTL build.

A later gate must typecheck/elaborate the exact selected source, execute both
default and opted-in owner paths with real Matrix arithmetic, verify actual
backpressure/terminal/fault/reset behavior, and compare same-input full cold
and carried outputs under unchanged thresholds. This deliverable has not run
those stages and makes no throughput, timing, resource, full-attention, or
full-forward claim.
