# Qwen2 M128 same-live Attention candidate

Default execution returns `NOT_EXECUTED`. The independent 27-AST, 18-output Attention reference is frozen. The one authorized full M128 process failed at its unchanged 570-second inner budget, before Attention terminal or oracle opening. No official pc0..12 numerical acceptance is claimed. The persisted authorization bit records that consumed one-run approval; it does not authorize a retry. The public failure record is `FAILURE.md`; `SUMMARY.json` records exact incomplete counts and hashes of locally retained evidence.

The runner is designed to keep one execution, host, physical map, Dense owner, Matrix service and Scalar service alive from fresh pc0 through pc12. In the only actual run it genuinely retired pc8 and the256 KiB KV copy, then stopped inside Attention. The intended successful boundary would retire public10/11 and hold completion12 with att fully ACKed but unpublished; this boundary was not reached. No finalfence, pc13 or fullblock completion is claimed. The nine readonly inputs are x/gamma0/QKV weights and biases/RoPE. Oracle tensors open only after the final output/observation seal.

## Additive PV32 schedule

`OfficialPV32AttentionOwner` retains the original QK/softmax AST and original profile0 arithmetic. It combines each pair of chronological PV16 groups into one PV32 group. The first/second V16 beats use the existing bv/packet holds. The existing wide Legacy reply stays outstanding while each BF16 output16 beat is written and ACKed; it retires exactly once after both ACKs. There is no private 32-word result cache or new C profile/kernel.

Selected32 finite checks happen before either final write. This intentionally changes the failure prefix: a bad high half may reject before the low write, whereas the original two-group owner can leave its low64B ACKed. Matrix native fenv diagnostics are separate from the actual selected finite policy; no architectural Matrix flag-equivalence claim is made.

M128 predictions, to be checked against a fresh complete run:
- Original profile0 QK/PV: 1,585,152 steps, 811,597,824 actual FMA
- PV32 QK/PV: 1,188,864 steps, 608,698,368 actual FMA
- Useful arithmetic remains 25,362,432 FMA; candidate useful/executed is 4.1667%
- Each step has 4096 full-array opportunities but executes only 512 slice0 FMA; full-array useful opportunity ratio is 0.5208333%
- Fixed physical accumulator remains 5×16×256 FP32 = 81,920 B

These arithmetic ratios and software functional ticks are not hardware busy fraction or utilization, which remain unknown.

## Bounded evidence

All evidence is in `work/qwen2_live_attention_numeric_m128_20261014/`:
- `calibration_v1`: original service/owner budget-only calibration
- `pv32_trace_v2`: original native ABI two16/one32 bit equality and held-reply probe
- `pv32_small_owner_v3`: 26 real-owner M1/M2 success/fault cases, including paired V read faults, low/high write faults, pending abort, Matrix wrong-done/error-without-result, intermediate finite rejection, and a separately scoped direct-ABI final negative-zero case
- `preflight_v3`: metadata-only official reference validation, original public21 pc0 request, candidate constructor/observer checks, zero Matrix/Scalar arithmetic and zero producer writes

Normal and optimized Python each pass 21 cold admission/isolation/source tests. The small gate checks that enabling the readonly observer changes neither successful bytes nor owner/Matrix/Scalar counts/ticks. Earlier failed trace/preflight attempts are preserved.

The independent typed Attention reference was deferred. No typed Attention bit-exact, future-position DUT observation, full29-node, RTL, EDA or whole-block acceptance is claimed. Causal scores/logits/probabilities each require 99,072 observed elements; all PV/context require 196,608. The explicit reference mask is checked, while the DUT implements causality by descriptor work selection.

This snapshot does not modify previous execution models, services, arithmetic, parser, pins, plans or indices. Its accompanying CI runs only the21 cold tests in each Python mode and the default NOT_EXECUTED path. The original numerical attempt remains a budget failure regardless of cold CI status.
