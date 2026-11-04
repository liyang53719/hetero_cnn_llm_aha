# Independent GDN32 bounded model tests

These tests are an independent proposed schedule/address/count/numerical-order model plus a small textual source-binding check. They do **not** instantiate, elaborate, simulate, compile, install, or publish the Chisel candidate. A pass is not evidence that the candidate implements this model.

Run from the candidate directory (the directory containing `source/` and `tests/`):

```sh
set -o pipefail
PYTHONDONTWRITEBYTECODE=1 timeout 30s python3 tests/test_gdn32_model.py 2>&1 | tee tests/MODEL_TEST_LOG.txt
PYTHONDONTWRITEBYTECODE=1 timeout 30s python3 -O tests/test_gdn32_model.py 2>&1 | tee tests/MODEL_TEST_LOG_O.txt
```

Base sources default to the nearest ancestor repository's `candidates/fresh_original_top_recovery_20261028/source`, independent of working directory. A sibling candidate layout is also supported. If the baseline is outside that repository, set its exact directory explicitly before either run:

```sh
export GDN_BASE_SOURCE_ROOT=/path/to/pinned/baseline/source
```

There is no dependency on the original workspace path. The candidate source is always read relative to these tests at `../source/GdnRuntimeChunkExecuteOwner32V1.scala`. Baseline files must match their recorded SHA256 pins. The candidate SHA256 and byte count are captured in each report.

The process enforces a 128 MiB address-space hard limit and a 29-second alarm. Only Python's standard library is used. No large tensors are allocated. Full phase schedules are streamed; numeric witnesses use at most bounded 128x32/64x32 tiles. Output is written only beside the tests. Normal and `python -O` runs write `MODEL_TEST_REPORT.json` and `MODEL_TEST_REPORT_O.json` respectively. The pre-portability evidence is preserved as `MODEL_TEST_LOG_r1.txt` and `MODEL_TEST_REPORT_r1.json`. Protocol checks use explicit exceptions, so optimization cannot disable them.

## Count formulas

All reads and writes below are 64-byte requests/ACKs. Let R/C/K be phase dimensions, G=C/32, F=1 for phases 5/6 and 0 otherwise.

- Dot: reads = R G (2 K + ceil(K/16) + 2 F); vector transactions = R G (2 K + F); writes = R C/16.
- Solve (phases 7/8, R=64, C=128): reads = (C/32) sum(r=0..63) [2r + ceil(r/16) + 2] = 17,264; vectors = (C/32) sum [2r + 1] = 16,384; writes = 512.
- Binary phases 10/13/16: reads = 2 R C/16; vectors = R C/32; writes = R C/16.
- Decay phase 15: reads = R C/16; vectors = R C/32; writes = R C/16.
- Materialize phase 17: R=16 for M16, otherwise R=64 per chunk; reads = 8R; vectors = 4R; writes = 4R. M128 has two chunks. The complete job across all heads writes tokens x valueHeads x 256 bytes.

Every phase halves vector transactions relative to the explicit16lane baseline. Scratch/output write bytes are unchanged. Dot/solve read reduction comes only from reusing each 16-coefficient A beat across the adjacent output halves. B/factor/RHS memory traffic stays real. Phase17 preserves both real FP32 reads and uses one 32lane format request per output beat.

## Full phases 5–17 aggregate counts

Counts are per head per chunk, including phase17 and excluding phases 0–4/18:

| Tokens | Width | Read beats | Vector transactions | Write beats |
|---|---:|---:|---:|---:|
| M16 | 16 | 354880 | 659072 | 7232 |
| M16 | 32 | 344416 | 329536 | 7232 |
| M128 | 16 | 355264 | 659456 | 7424 |
| M128 | 32 | 344800 | 329728 | 7424 |

For the full M128 work across both chunks, multiply the M128 row by two and by valueHeads. For M16, multiply by valueHeads only. M16 phases5–16 retain the padded 64-row chunk schedule; only phase17 uses 16 active rows.

The DDR path remains 512 bits / 64 bytes. The candidate saves 10,464 coefficient read beats per head/chunk but leaves all B, RHS, factor, binary, format-input and write traffic intact. For M128, total memory transactions are 352,224 versus 362,688 (about 2.89% fewer), despite 50% fewer vector transactions. This is **not** a bandwidth doubling or measured speedup; no cycle/QoR improvement is established without actual latency/backpressure evidence.

## Coverage and interpretation

- Static candidate-source anchors bind the 32lane payload, three1024-bit registers, 16-coefficient access, 17264 solve reads, 16384 solve vectors, single phase17 format, and 64B memory halves. This is source text inspection, not execution or compilation.
- All 13 phases, exact baseline source pins, phase dimensions, complete streaming counts for width16 and width32; full memory-address multisets and matrix-span bounds. Only coefficient-read multiplicity halves, with every other address multiplicity unchanged.
- Ascending coefficient K, 16-coefficient boundaries, low/high B/factor/RHS pairing and write order; binary and decay addressing.
- M16/M128, 16/32 value-head layouts, all heads and chunks for phase17, complete output address coverage without duplicates, previous-state selection, span/alias/layout negative cases.
- Unit-lower dependency: row0 has no coefficient or previous-row reads; only k < row coefficients are selected; every preceding row's eight write ACKs precede its use. A physical 64B coefficient beat can include an unused diagonal word, so “no diagonal read” means no diagonal selection or separate diagonal request, not that the enclosing beat cannot contain it.
- Separate exact-integer FP32 multiplication then addition with RNE at each step and +0 initialization; per-lane serial16/paired32 comparisons; cancellation/reassociation and FMA counterexamples; solve, binary, factor and decay witnesses.
- BF16 RNE ties on both signs, subnormal boundaries, signed zero, low/high packing, nonfinite and format-overflow negatives.
- 64 rejected schedule mutations cover omitted, reversed, aliased and early-use halves, plus reversed write halves.
- 39 deterministic seeded phase/backpressure witnesses with held requests, ACK barriers and matching identities. Fault negatives cover unsolicited/duplicate/mismatched results and backend error. This is an abstract serial protocol model, not a cycle-accurate implementation.

Not covered: candidate Scala compilation, candidate FSM correctness, actual Chisel/RTL ready/valid behavior, complete job/predecessor admission, stale/global ownership, backend numerical flag policy, synthesized resource count/timing/QoR, or full end-to-end tensors. No hardware or compatibility acceptance claim is made.
