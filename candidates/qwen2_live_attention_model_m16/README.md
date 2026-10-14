# Qwen2 M16 fresh live Attention localization

**PASS for the original scoped BF16 numerical gates. Not fully bit-exact.** The single fresh `m16_pv32_actual_v1` attempt completed in 44.205 host seconds (525,084 KiB peak RSS). Its independent saved-byte review passed. [SUMMARY.json](SUMMARY.json) records receipt paths, sizes and SHA-256 identities; numeric payloads and logs remain in ignored work directories.

## Executed boundary

The nine readonly M16 inputs freshly produced QKV at public pc0..8, then continued through pc9 KV and fused pc10..12 causal PV32 Attention in the same public21 execution, physical memory and shared Matrix objects. No saved QKV was injected. All 188 frozen execution sources, tools and inputs matched before/after. The independent fresh M16 reference uses 27 original official AST nodes and 18 exports; no M128 reference slicing is used. Oracle payload reads occurred only after pc12 output/observation seal.

There are 11 owner terminals and 12 public completions. Completion pc12 is held, all backend debts are drained, and all 98,304 Attention output bytes are ACKed. `att` is unpublished; no final fence or pc13/suffix execution occurred. This is neither full-block nor full-29-node acceptance, and makes no RTL/EDA or hardware-utilization claim.

## Numerical result and limits

The unchanged, pre-run-frozen `spec/numerical_contract.md` SHA-256 is `5cf7f538577e171ad42d70de60a24907b27e59991cc4d3895c42885fec962bb5`. Original BF16 operator limits are max absolute error 0.03125 and mean absolute error 0.005; no threshold was changed after observing results.

- Six official prefix nodes (`n0`, `qr`, `q`, `kr`, `k`, `v`), KV exact-copy, and observed causal scores/logits are bit-exact.
- Probability has 23 differing elements out of 1,632, max absolute error 1.806e-35. PV and `att` each have one difference out of 24,576, max absolute error 0.00048828125. All applicable original BF16 gates pass.
- `softmax_fp32` is diagnostic, with official element verdict **null**. Its independent original probability-row-sum gate passes: max error 1.788e-7 <= 2e-5 over 192 rows.
- `qraw`, `kraw`, `vraw` were actually produced and sealed, but this run reports `NO_OFFICIAL_RAW_REFERENCE` and did not execute the older independent typed-raw verifier. No old typed PASS is inherited. Typed Attention bit-exact verification was not executed.
- Each score/probability field observes all 1,632 causal positions of 3,072 logical positions. The 1,440 future positions have no DUT observation; original causal descriptors skip their work. The explicit official BF16 causal mask is checked separately. All PV/context elements are observed.

The sole PV difference is at head 3/token 7/dimension 115. Actual FP32 accumulation `0x3de98000` is a BF16 midpoint and rounds correctly to even (`0x3dea0000`); official BF16 is `0x3de90000`. The entire causal BF16 probability row matches. Official pre-rounding FP32 PV is not exported, so this does not establish its reduction/rounding root cause.

## Actual functional accounting

Attention accepted 19,584 Matrix steps, executing 10,027,008 C FMA with 417,792 useful FMA. Original QK predicts 13,056 steps; PV32 predicts 6,528 rather than the old two-group PV's 13,056. The prediction matches this fresh observation; no full old-path baseline was rerun. Attention has 158,161 functional driver ticks; the complete pc0..12 prefix has 524,228 host-model ticks. QKV separately executes 98,304 wide Matrix steps and 402,653,184 FMA.

KV exact-copy covers 32,768 bytes: 512 distinct 64-byte coverage beats and 512 actual write ACK events. Attention writes 1,536 64-byte ACKed outputs. Whole-prefix DDR byte/event totals, Scalar calls, owner/service state partitions and waits are in SUMMARY. State partitions overlap ownership/wait counters and must not be summed together. Owner partitions include the admission tick; driver ticks exclude it.

Fixed storage remains five 16x256 accumulator contexts (81,920 bytes). Attention's 417,792 useful FMA are 4.1667% of 10,027,008 executed FMA and 0.5208333% of 80,216,064 full-array opportunities. These ratios are arithmetic fill measures, not hardware busy fraction; hardware cycles/utilization remain null.

## Separate host-cost experiment and cold gates

Synthetic M8 public3 cost v1 failed in the monitoring-timer testbench and is preserved. The authorized v2 timer-only fix completed all eight Harness/public-physical x observer off/on x timer off/on conditions with identical output bytes, ACKs, owner/service/Scalar counters and ticks. These are synthetic stimuli, not real M16 inputs. Timings are single fixed-order software measurements, including timer-probe overhead; they do not establish architectural speedup. Frozen v2 source snapshots remain separate from later unused runner/telemetry changes.

The actual used 105-second inner/120-second outer bounds, 2 GiB address-space limit, one-thread environment and original CPU affinity 0..8. Normal and `-O` cold suites each pass 20 tests without arithmetic or actual-input work directories. Default entry returns `NOT_EXECUTED`; the authorization pin records the consumed single attempt, not standing permission for reruns. New-scope failure telemetry preserves stage, original cause, owner/debt state, oracle read list and peak RSS. The older failed M128 attempt and its 169 frozen execution sources are unchanged.
