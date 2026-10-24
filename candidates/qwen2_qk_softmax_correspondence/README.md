# Pinned Qwen2 QK16 cell-map and source-topology gate

This is a **source projection**, not model, Scala, RTL, arithmetic, timing, or
full-block acceptance. A successful run deliberately returns **INCOMPLETE,
exit 2**. A missing, changed, or unrecognized input returns **REJECTED, exit 1**.
There is no full-acceptance exit path.

## Concrete uncertainty closed

The executable check reads the actual composed Python QK request and its actual
`selected_words` consumer, and the historical production Scala initial-result
and retained-result selections. It enumerates key-tail sizes 1 through 16:

- Python selects `(row, 16 * local_key + row)` in key-major, lane-minor order.
- Both Scala selections use `(lane, (packedSelected << 4) + lane)`.
- All 2,176 ordered coordinate comparisons agree; the complete tile has 256
  unique selected cells, bounded by the 16 by 256 result interface.

Only integer cell coordinates execute. No production Python module is imported;
no FMA, BF16, exp, softmax, native library, Scala elaboration, or RTL executes.
Tail enumeration is not a token/prefill run and is never presented as M128.

The same recognizer checks pinned syntax for the ordered 16-lane scalar fold,
completed-dot materialization, scale multiplication, score materialization, the
same score feeding storage and max, and score-minus-max feeding exp. These are
**symbolic source boundaries**, not numerical equivalence. In particular, the
Python scale literal and Scala headDim-dependent expression are recorded, not
numerically compared. Parser recognition is deliberately narrow, not a generic
Python/Scala equivalence proof or control-flow interpreter.

## Exact targets, not a relabelled snapshot

Source reference: `liyang53719/hetero_cnn_llm_aha` at
`cacc259d8893754b8cae968b5355ccf37e5b79cf`.

Selected Scala:

- `development_snapshots/canonical_host_observation_taps_source_20261017/baseline/Qwen2Block.scala`
- SHA256 `31b618680b4c750398a0dcf21fa34185dd9fc9b1732e370cfce502915814bd68`
- This is the Qwen2Block postimage named by
  `candidates/qwen2_resident_matrix/production_qk16_rebase/POSTIMAGE_PINS.json`.
  This gate binds that one postimage, not the complete five-file production
  installation, host wiring, or the model-run source tree.

Bare main Scala at the reference commit:

- `chisel/continuous_prefill/src/main/scala/heteronpu/continuous/Qwen2Block.scala`
- SHA256 `9572763a636e77362f82d9fb6d8d9bc823be2ef1beda88929e227abd78a4b2d4`
- **MISMATCH**: lacks the selected production QK16 enable/selection path and
  official materialization helper, and has a different `attScore` body.
  The historical postimage must not be described as current main production.

Python:

- Base `candidates/qwen2_resident_matrix/attention_packed_owner/schedule.py`
- Compose the exact `attention_packed_m16/m16.patch`, then
  `attention_packed_m128/tiled.patch`, in memory with no patch command, fuzz,
  offsets, or filesystem installation.
- Derived SHA256 `a65dca9d24862c2b552117ce2c9cfdb270215b12881490fc50b5545b938b6086`,
  independently required by existing `attention_packed_m128/pins.json`.
- Consumer: `attention_packed_owner/client.py::PackedResult.selected_words`.

`SOURCE_PINS.json` binds the exact ten input bodies, including the existing
postimage ledger, composed-schedule pin, and two historical receipts. The gate
hashes bytes; it does not authenticate Git history, remote freshness, or signing.
Source changes require a separately reviewed pin/recognizer change, not a flag
to skip identity checking.

## Historical qualification is preserved, not inherited

The byte-bound historical receipt remains
`PASS_FRESH_SAME_HOST_M128_ASSIGNED27`, commit
`8ba333c76722b47b681be88612b1c6987e34a5f4`, run `39017864296`.
It is a genuine 128-row cold model-layer run, not two M1 calls, with 27 assigned
official gates and 28 observed semantic stages. This tool does not reexecute or
revalidate its private numerical bodies and does not inherit its acceptance.

The archived model identity is `Qwen/Qwen2-1.5B-Instruct`, revision
`ba1cf1846d7df0a0591d6c00649f57e798519da8`, layer 0. The existing upstream pin
is Transformers 4.40.1, commit `9fe3f585bb4ea29f209dc705d269fbe292e1128f`,
with `modeling_qwen2.py` SHA256
`f1c7a117ced20ee632e4c17d09982863304d6e30bb44f0ccdebd4b27dde259ad` under
`config/upstream/weight_headers/qwen2_1p5b/`. These are upstream reuse references,
not newly executed or numerically qualified by this source-projection gate.

The full-29 gap is unchanged: `explicit_mask_tensor` is unobserved;
`softmax_fp32` is observed but diagnostic only, with no approved official FP32
elementwise tolerance. The causal observations do not establish future-mask
cells. No mask values or new tolerance are created here. This does not invalidate
that narrower historical model PASS or promote it to Scala/RTL acceptance.

## Explicitly incomplete

The report keeps all of the following `INCOMPLETE`, even when this slice passes:

- Six-head scheduling, shared-bank scratch/ACK/release, the physical 384-byte
  panel, PV6 supply and context retention, final all-resource debt join, and
  Scalar exception-policy equivalence.
- Whole-block source binding and current-main production integration.
- Explicit mask-tensor observation and official softmax-FP32 acceptance.

The next control correspondence must use the actual six-head Python schedule
and the chosen Scala postimage's per-head softmax/PV path, with an explicit
mapping or implementation change. Cell-map agreement cannot establish their
scheduling or ownership equivalence. No old long RTL run is restarted.

## Cold reproduction

From a repository root containing the exact pinned source paths:

```sh
timeout -k 2 30s python -I -B candidates/qwen2_qk_softmax_correspondence/test_gate.py --source-root .
timeout -k 2 30s python -I -B -O candidates/qwen2_qk_softmax_correspondence/test_gate.py --source-root .
timeout -k 2 20s python -I -B candidates/qwen2_qk_softmax_correspondence/gate.py --source-root .
```

The last command must return 2 with a JSON `INCOMPLETE` report. Test exit 0 means
the bounded source gate behaves as specified, not that Qwen2 passes a new model
or hardware qualification. Tests cap their own process to 20 CPU seconds,
256 MiB address space, and one allowed CPU. Only temporary mutation files are
written; production fixtures are read-only and rechecked.

Coverage includes cell transposition and selection order, differing initial vs
held selection, both wrong Scala shifts, selected-word consumer mutation,
rounding boundaries, fold order/length/initialization, score/max/storage routing,
softmax subtraction, finite guard, patch target/offset/context/counts, hash and
symlink rejection, CLI non-acceptance, and preserved historical scope. The same
tests run with normal Python and `-O`; safety checks do not rely on `assert`.
