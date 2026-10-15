# Bounded QK ACK/phase candidate

This small default-off event wrapper reuses the published
`qwen2_rectangular_qk_payload` kernel and physical A/B byte arrays unchanged.
The actual native payload execution supplies every partial, dot and score.
There is no second numerical engine and no reference injection. Its input A
contents come from an explicitly precommitted **synthetic fixture**; real input
DMA/readiness and upstream cache ownership are outside this batch.

## Implemented model boundary

- Exactly one accepted operation/return is outstanding. Every tag includes
  epoch, tile, sequence, kind, stripe/context/step and physical bank address.
  Rejected admission has no side effects. Wrong response identity poisons and
  retains the original accepted return for drain.
- Five native contexts and five B partial slots are used in groups 5/5/5/1.
  Every Matrix step has an explicit return ACK, including non-terminal steps.
  The frozen native kernel performs the selected-causal finite check each step.
- The one existing 16-KiB `finalValue` is held while each real 32-byte B bank
  word is written and acknowledged. A partial slot is valid only after all
  those commits; the corresponding context stays owned until then. New groups
  wait for every prior partial's ordered fold and final score-write ACK.
- Fold uses actual B/A 32-byte read responses, one scalar Add response, then
  an A-word read/modify/write and commit ACK. The original +0 start, 16 stripe
  order, legacy scalar errors and two post-dot BF16 boundaries are unchanged.
  The scale operation similarly returns through one scalar response before its
  score write. No vector speedup or overlapping scalar engine is invented.
- Successful owner completion follows a separately acknowledged owner terminal,
  after all score commits and group terminals. Lost ACKs never imply success.
  Abort stops new requests and retains the accepted one. A valid successful
  write ACK after abort still commits its accepted physical bank write, but no
  slot/output becomes publishable. Error ACKs poison; this test backend models
  failed writes as not committed, without making a pristine-output promise for
  real failed hardware writes.

Payload storage remains A688KiB/B80KiB, five accumulator contexts totaling
80KiB, and one existing finalValue16KiB. The original single-KV-head 84KiB A
layout remains unchanged. The host uses bounded RMW temporaries for one operation; concrete register
allocation is not yet established. There is no extra tile, unbounded request
queue or result FIFO borrowing. The observer is a testbench tap only. Old profiles/readers
are unchanged; `old_owners_idle` is an explicit assumed integration precondition,
not evidence that RTL arbitration has already been connected.

These are event handshakes, **not cycles**. In particular, constructing a Matrix
input still records all source A bank reads rather than implementing its gather
response pipeline. At full 16Q×128K, one payload needs nine reads per A bank with
the original token-major layout. B writes are one 32-byte bank word per modeled
transaction. Scalar/partial/score operation counts and accepted acknowledgments
are separate from `enabled_cell_fmas` and the fixed4096-lane issue capacity.
Hardware cycles/utilization remain null; no ≥80% performance claim is made.

## Concrete implementation cut, still pending

Existing `BurstProtocol.scala:21–39` has Matrix group/step/result/done/abort;
`MatrixPipeline.scala:49–77,93–138` already provides five-context ownership,
eight metadata credits, two result tiles, normal physical routing and drain.
The old `LegacyMatrixStreamClient` at lines145–185 binds context0 and waits for
each result. Python `ffn_attention/matrix_service.py:318–368` and its native
`matrix_numeric.cpp:181–235` likewise need a new explicitly enabled profile;
the old modes must retain their admission and non-emit/result-reader semantics.

The smallest conservative first Chisel adapter can emit **every** new-QK step,
check causal finiteness on each actual result, and store only the last step.
That uses the existing result interface without inventing a non-emit side tap;
128 returns/tile must be charged, rather than assuming only16 partial returns.
Suppressing those intermediate payload returns later requires a new internal
selected-lane checker/metadata route, not removal of an existing reader.

A new B32-byte physical word write/commit route is required. Existing
`ffn_tiles/model.py:69–79,150–245` and `tile_ports.patch` are A-bank three-slot
read-modify-write interfaces, not five B slots. The producer result must remain
held or captured in finalValue until every B commit ACK. Existing Dense bank
and TileBank APIs cannot simply be relabeled to obtain this route.

Scalar service is available in `Qwen2Block.scala:98–114`, with real one-request
ownership; `BlockFloat.scala:29–30,55–81,108` holds results and preserves fatal
flags. Core Vector16 Add/Mul exists at `Qwen2Block.scala:128–130`, but is internal,
has no lending handshake and currently drops exception flags. Moving independent
score lanes onto it requires a new owner-gated packet/flag interface and the
same per-score stripe sequence. Softmax Exp/Div remains the existing iterative
Scalar path; vectorizing probability sums must not reassociate the original
ordered sums. Scalar call counts are work, not completion-cycle predictions.

## Small next regressions, not run here

1. New profile default-off rejection and old-profile/non-emit-reader regression;
   enabled five-context/eight-step canonical progress, wrong tags and abort.
2. Selected-causal finite on every result under backpressure, with noncausal
   nonfinite cells ignored; fixed2 result credits plus finalValue/store holds.
3. Partial B commit/ordered fold boundary: missing/wrong ACK, early group/context
   reuse, and final Scalar/score-write/owner terminal ordering.

Small Chisel tests will elaborate/emit test RTL if a simulator is used, and that
must be recorded explicitly. No Chisel, RTL emission/simulation or full business
run has occurred in this batch.

## Reproduce

```sh
/workspace/shared/hetero-contracts-venv/bin/python -m pytest -q candidates/qwen2_rectangular_qk_phase/test_model.py
/workspace/shared/hetero-contracts-venv/bin/python -O -m pytest -q candidates/qwen2_rectangular_qk_phase/test_model.py
```

Eight tests join actual payloads to ACKs and compare all observed partial/dot/
score bits with the frozen tiny runner; cover default-off, single credit, missing
B ACK, wrong epoch, abort with accepted write, Scalar/score/owner ACK ordering,
numeric/write errors, and forged admission addresses. The upstream tiny runner's
independent integer numerical checks remain the arithmetic evidence.
