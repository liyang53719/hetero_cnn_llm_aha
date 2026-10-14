# REJECTED_FOR_PROMOTION_PERFORMANCE_REGRESSION

Functional status: PASS_M2_PER_EDGE_M8_FINAL_STATE_ABBA_ONLY.

This is new publication metadata. The executed 194-source closure, its receipt,
and the execution-time README remain unchanged.

## Decision

Keep the original default. The sole six-arm experiment completed successfully in
29.851 seconds, but V1 failed the performance gate. Both
balanced M8 pairs were slower in wall and CPU time despite a 100% fast-path hit
rate. No guard was relaxed, no numeric run was retried, and no Host-tail or M128
run was launched.

## Measured result

| M8 observed, recorder-free | Old wall | New wall | Old CPU | New CPU |
|---|---:|---:|---:|---:|
| AB pair | 3.101946 s | 3.632880 s | 3.101506 s | 3.632379 s |
| BA pair | 2.956332 s | 3.556249 s | 2.955976 s | 3.555626 s |
| Median | 3.029139 s | 3.594565 s | 3.028741 s | 3.594003 s |

Median wall cost increased **18.67%**.
Each new M8 arm recorded 44,037 fast hits and zero fallbacks. The original idle
wrapper makes two dynamic ports calls; V1 makes one while checking 38 descriptor
slots and 16 code identities. The end-to-end result does not isolate guard cost
from other overhead, and is not a hardware or architecture-speedup measurement.

## Exact scopes and work

- Complete recorded public3 M2 old/new: 4,445 actual driver ticks; 4,446 real
  Host/Dense/Tile edges; 768 reads; 192 ACKs; 432 Matrix steps; 221,184 C FMA calls.
  All 4,446 edge records match byte-for-byte (67,671,680 decompressed bytes).
- Complete public3 M8 observed ABBA, without the Dense recorder: each arm has
  44,036 actual driver ticks; 44,037 real Host/Dense/Tile edges; 7,680 reads;
  768 ACKs; 5,184 Matrix steps; 2,654,208 C FMA calls.
- Within each scope, complete final control/backend state, raw output, physical
  ACKs, all ten observation buffers and their reports, and Host traces match.
  M8 per-edge equality is **not** claimed. Both fixtures retain 12 causal heads,
  two KV heads, head dimension 128, and independently pinned metadata/stimuli.
- M2 captures actual Dense returns through a separate read-only monitoring ID.
  All control fields, ordered counters and aliases are recorded each edge.
  Unchanged Dense SRAM contents are factored from complete initial/final words,
  source-bound clean/debt-free state, actual empty access events, and stable
  bank/word-array/row identities. These are not freshly hashed per-edge banks.
- Every arm leaves the original public completion held. `att` is fully written,
  ACKed and terminal, but unpublished. This is not full public21/block acceptance.

## Provenance and launch boundary

Execution receipt: `work/qwen2_attention_idle_fastpath_20261014/m2_recorded_m8_abba_v1/RESULT.json`

SHA256: `919941dc290317a5566c3275bbdc6d41706aed1e7479972a196a470e41be803a`

Reviewed manifest SHA256:
`4dfe2fbb01091ab3612d4ae47c843fe36ec62e8de3f1ab25014f4b4352349b82`

All 194 source hashes and tool hashes match before/after and the current files.
The failed M128's 169-source and actual M16's 188-source closures remain unchanged.
The immutable execution-time README SHA is
`abcf804b370e9c6baf27b769994e65e3660953f8b8371fec337397baf91ac8a9`.

Six isolated processes used pinned CPython 3.12, the same verified unchanged ELF,
CPU 0, and OMP/MKL/OpenBLAS threads=1. The parent used the exact planned GNU
`timeout --signal=KILL 45s` supervisor command. That GNU process group does not
itself cover the probe's independently created worker sessions. The reviewed
probe additionally has a 44.5-second alarm, a start+43-second worker deadline,
and explicit active-child `killpg`/reap cleanup. The normal run exited 0 in
29.851 seconds; timeout cleanup was not needed. The separately prepared
`work/qwen2_attention_idle_fastpath_20261014/launch_once.py` process-tree launcher
was **not executed** and must not be credited as the actual watchdog.

Only two exact verified Matrix-resource address fields are normalized for ASLR
in comparison artifacts. Real process addresses remain in each arm's provenance.
No generic ID stripping, model methods, original PV32 callbacks, arithmetic,
resource allocation, scheduling policy or event order was changed.

## Earlier gates and next step

The owner cold suite passed 7 tests with 1,193 full state/event/alias comparisons,
including real ordinary/window/tile/drain/reset paths and post-drain fast hits.
The final recorder/integration suite passed 16 cold tests; independent source
and monitoring-interference review approved only this bounded experiment.

The initial full-M8 recorded-pair plan was rejected before arithmetic because
cold recorder cost exceeded the 45-second envelope. The parent separately
approved full M2 recording plus M8 ABBA; the frozen conservative prediction was
37.57 seconds. Original and revised cold receipts remain preserved.

V1 is retained as a negative result, not a production selection. No further
execution is authorized by this report. A different optimization needs its own
scope and review; these measurements establish no M128-under-570-second budget.


## Post-run diagnostic limitation

Independent read-only review found that `snapshot_load` cannot reconstruct one
actual saved frame shape: a pickled bound method refers to a persistent anchor
that this helper represents as a tuple, so `fetch_command` lookup raises
`AttributeError`. Old/new recorded streams are byte-identical and the actual
equality comparison did not invoke this decoder, so the measured equivalence
and negative performance result remain valid. Detailed first-divergence
explanation is not reliable for that frame shape. A mismatch still raises and
fails the run; it is not silently accepted, but its intended detailed divergence
record can be absent. No executed source was
changed and no numerical rerun was performed. Any future reuse should repair
and review that diagnostic in a new version rather than relabel this receipt.


## Independent actual-result review

`work/qwen2_attention_idle_fastpath_review_20261014/ACTUAL_V1_REVIEW.json`

SHA256: `7978ffddcb6fca77d03d28cb833383621a0e4772492e2f36efc0323574ea49b5`

Verdict: `PASS_READ_ONLY_V1_REAUDIT_REJECT_M128_PROMOTION`. The review checked
source/tool/fixture and verified ASLR correspondence, all six final-state/raw/
trace/ten-buffer records, and the balanced regression. Its read-only symbolic
persistent-root decoder independently reconstructed all 4,446 M2 records:
768 reads, 192 writes and ACKs, 432 Matrix requests/results, and exactly one
job admission, owner response, Host request and Host result. This inspection
did not change saved evidence or frozen code and did not execute arithmetic.
The original diagnostic decoder limitation remains documented above. The
parent's full invocation measured 29.963775 seconds (exit 0); the probe's
internal supervisor receipt measured 29.850834 seconds. Neither establishes
a full-public21 or M128 bound.
