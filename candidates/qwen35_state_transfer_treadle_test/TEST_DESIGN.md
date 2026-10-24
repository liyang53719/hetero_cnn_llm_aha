# Cold M16/head0 real-owner test source

Status: source prepared only. Not compiled, elaborated, instantiated, lowered or run. No dependency acquisition, installation, RTL generation or external simulator invocation was performed. A proposed time budget is not execution authorization; the parent supplies a separately reviewed scope runner and admission.

The single ScalaTest case names the unchanged `heteronpu.continuous.GdnChunkStateTransferOwner` directly and explicitly selects `chiseltest.simulator.TreadleBackendAnnotation`. It adds no wrapper hardware, replacement FSM, arithmetic model, SecurityManager or generic runner.

## Intended checks, not claimed results

- One accepted cold M16/head0 Initialize job. Five aligned, complete, disjoint address spans and an invalid generation-zero committed root.
- Exactly 1,024 accepted write requests. Independent literal oracle: `scratchBase + 64 * index`, tag `(0xa1b2c3d4 << 32) | index`, 64 one-bit mask enables, and a zero 512-bit payload. No read request is permitted.
- Each request stalls for `1 + index % 3` cycles and is checked on every stalled cycle and the acceptance edge: 2,047 intended request-backpressure cycles.
- Every fourth beat presents a matching zero-latency response on the request acceptance cycle. The owner must hold ready low there; valid/tag/data/error are left unchanged through the next cycle's ACK. This supplies 256 intended real response-valid/ready-low cycles without acknowledging an unaccepted request.
- Other beats delay ACK valid by `1 + index % 4` cycles, totaling 2,304 cycles. During every response wait, no next memory request or done is allowed and byte credit cannot advance. Response data is deliberately nonzero and ignored by this cold zero-fill path.
- Exactly one response per accepted request, only matching tag and error=false. `MemoryResponse` contains data/tag/error, not nbytes or direction; the scoreboard credits 64 bytes from the validated outstanding full-beat write only on response.fire. The result must report readBytes=0 and writeBytes=65,536.
- Every busy cycle checks job.ready=false, done.valid=false, resetRequired=false, ACK-accounted writeBytes, and exact active cycles. A different second job stays offered throughout busy and held-done time; it is blocked even on the done.fire edge. The trace ends immediately after observing idle, before an idle edge can accept that offer.
- All ten result fields, including cycles=6,399, must remain unchanged during eight held-done cycles. Success requires transferComplete/localDrained=true; completion returns to idle with memory.valid=false.
- The sole explicit `clock.step()` call is guarded at 20,000 steps, and `clock.setTimeout(20000)` is also set. The deterministic source schedule expects 6,412 explicit test-issued steps including reset, launch, held done and retirement. Chiseltest's own initialization is outside that explicit count and must remain inside the runner's separately enforced total budget.

## Sources inspected

- Frozen owner: `candidate_qwen35_chunk_state_transfer_20261021T1334/source/GdnChunkStateTransferOwner.scala`.
- Contract: `candidate_qwen35_chunk_contract_20261021T1245/source/GdnChunkProtocol.scala` and `GdnChunkAddressPlan.scala`.
- Actual MemoryRequest/MemoryResponse/Status APIs: `recovery_public_main_20261020T0454/chisel/continuous_prefill/src/main/scala/heteronpu/continuous/Protocol.scala`.
- Existing style: `recovery_public_main_20261020T0454/candidates/qwen2_resident_matrix/dense_a_hold_chisel/AHoldUnit.scala`, its `dense_a_hold_interpreter/harness.patch`, README, source pins and 106-JAR dependency-lock metadata. Existing checked-in owner tests provide the `clock.setTimeout` API usage.
- The existing interpreter design pins upstream chiseltest 6.0.0 commit `d764fdf74652426b57c6eae00d71eac19effd224`; its inspected `dense_a_hold_interpreter_plan/upstream-source-identities.json` records official source URLs and hashes. No upstream bytes or JARs were newly acquired for this source-only work.

No warm/export/fault matrix, M128, FP32 math, final root publication, complete chunk/GDN correctness, DDR behavior, performance or utilization claim follows from this first test, even if it later passes. No current result exists.
