# Independent BF16 RoPE candidate review

Review base: `2754234`. Scope: the separately named all-products-BF16 candidate, its integer oracle, host-C reference, emitted HardFloat use, full-node traces, testbench protocol, and evidence boundaries. This is a component review, not production/full-model/PPA signoff.

## Findings and disposition

### R1 — P2, resolved: BF16 trace representation mismatch

Initial testbenches zero-extended actual 16-bit BF16 ports into the low half of their 32-bit trace words, while the oracle and immutable native fixtures encode BF16 by appending 16 zero low bits. For example, BF16 1.0 appeared as `00003f80` versus required `3f800000`.

- Evidence: `tb/tb_rope_bf16_candidate.sv` trace packing and `tb/tb_fp32_to_bf16_candidate.sv` expected/output packing.
- Consequence: the component gate rejected correct nonzero BF16 outputs; hardware arithmetic was not implicated.
- Target: verification/trace serialization, both wrappers and standalone converter.
- Fix: serialize `{bf16,16'd0}` consistently while leaving the physical DUT output port at 16 bits.
- Acceptance: actual 25-column DUT traces and standalone converter traces match the integer/C/native representations. Completed in the official run.
- Waiver: none needed; corrected.

### R2 — P1 tooling data-loss defect, resolved: input/output path aliases

The original C helper only rejected identical path strings. Passing a relative input path and its absolute equivalent as output returned success and truncated the input to zero bytes. The same issue applied to symlink/hardlink aliases.

- Evidence: `scripts/rope_bf16_candidate_reference.c`, optional `--input`/`--output` handling; independently reproduced on a disposable review file.
- Consequence: deterministic loss of caller-supplied file data in the standalone reference CLI. No RTL consequence and no effect on official runner arithmetic evidence, which uses stdin/stdout pipes.
- Target: software reference file I/O, not an arithmetic hierarchy.
- Fix: inspect the opened input with `fstat`, inspect the output target with `stat`, compare device/inode before opening the output for truncation, and fail closed on unexpected lookup failures. The helper explicitly excludes concurrent path replacement.
- Acceptance: relative/absolute, hardlink, symlink, reverse aliases, and redirected-input regressions preserve original bytes and return failure. The independent recheck covers absolute aliases, hardlinks and symlinks; all passed. Evidence: `independent_c_alias_review.json`, plus six implementation-worker regression tests.
- Waiver: none needed; corrected. The source-bound full component gate must use the post-fix C source hash recorded in the final evidence review.

No unresolved arithmetic or transaction defect was found in the reviewed candidate. Broad repository tests are a separate matter: their recorded five failures are not converted to a PASS by this review.

## Reconstructed hierarchy and transaction ownership

### Two-slot combinational-arithmetic wrapper

`fp32_rope_pair_bf16_candidate`

- An input payload/valid register owns one accepted pair.
- Four constant-multiply `HeteroFP32Alu` instances produce ec/os/es/oc and independent FP32 flags.
- Four `fp32_to_bf16_rne_candidate` instances convert each product.
- Two constant-add `HeteroFP32Alu` instances consume widened BF16 products, with bitwise sign inversion of os for the even lane.
- Two converter instances form the actual 16-bit terminal outputs.
- A second elastic slot holds output data, all trace fields and aggregate flags.
- `in_ready = !input_valid || !output_valid || out_ready`; output transfer is exactly `out_valid && out_ready`.

### Registered-primitive wrapper

`fp32_rope_pair_bf16_pipe_candidate`

- One transaction is owned by the FSM: IDLE, MISSUE, MWAIT, AISSUE, AWAIT, OUT.
- Four real generated `HeteroFP32MulPipeTag12` instances issue together and are consumed together.
- Four product converters are captured on MWAIT completion.
- Two real generated `HeteroFP32AddPipeTag12` instances issue together and are consumed together.
- Two terminal converters are captured on AWAIT completion.
- The OUT state holds all payload/trace/flags until the output handshake. A new external pair cannot overwrite the owned transaction.
- Internal tags are constant lane identifiers; transaction isolation and fixed lane wiring establish ownership, rather than a multi-transaction reorder structure.

Both wrappers clear their own payload/trace/flags/counters asynchronously. The generated primitive pipeline valid state resets synchronously, so reset must span the declared rising clock edges. This condition is explicit in the contract and tested; it is not a claim about physical reset recovery/removal timing.

## Arithmetic, special values, flags and trace review

- Inputs remain arbitrary raw binary32 words; there is no implicit input BF16 preconversion.
- Each FP32 multiply/add rounds separately under RNE. The emitted primitives and C volatile/no-inline operations retain separate stages; no FMA is substituted.
- Zero signs, exact cancellation, positive/negative subnormals, finite overflow, infinity, qNaN and sNaN paths were reviewed.
- FP32 and BF16 conversions use deliberately distinct underflow definitions. Binary32 follows pinned HardFloat precision/unbounded-exponent after-rounding tininess; the BF16 converter uses inexact plus zero destination exponent.
- BF16 finite RNE uses both the discarded half and retained parity. Overflow reaches signed infinity with OF|NX. Exact infinity/zero preserve sign. Canonical positive qNaN is returned, with NV exactly for sNaN conversion inputs. DZ is always zero.
- Product order ec/os/es/oc and output order even/odd agree across the oracle, RTL wiring, C helper, memory packing and emitted trace.
- All twelve five-bit exception records are preserved individually and OR-reduced to aggregate flags. Conversion overflow can create an infinity subsequently participating in invalid arithmetic; the directed corpus checks this sequence.
- The C comparison's permitted min-normal UF exception is narrow, documented and separately reported. The reviewed final run used **zero such exceptions**, so all observed C node flags agree exactly with DUT/oracle flags.
- Integer-oracle and host-C arithmetic are distinct implementations. C canonicalizes NaN result bits after arithmetic and retains actual host fenv flags, checks RNE/gradual underflow/sNaN support, and rejects FTZ/DAZ instead of repairing flags from the Python oracle.

## Independent additional evidence

### Conversion algorithm

`independent_converter_review.py` builds the complete positive finite BF16 value set in exact units of the smallest FP32 subnormal. It searches for adjacent BF16 values and compares exact distances/tie parity. This deliberately avoids the candidate's rounding-bias algorithm and RTL's discarded-bit increment structure.

- 1,703,936 comparisons; zero mismatches.
- All 65,536 high words at five rounding boundaries.
- Exhaustive 65,536 lower words for 20 signed zero, subnormal/normal, even/odd tie, finite/infinity and NaN boundary bins.
- 65,536 additional independently seeded arbitrary words.
- Normal and optimized Python execution passed; failures use explicit exceptions, not removable assertions.
- This is not exhaustive enumeration of all 2^32 input words.

### Protocol

`tb_independent_protocol.sv` and `independent_protocol_review.py` compile the actual pinned generated primitives with each candidate. A separate handshake queue checks 1,024 distinct exact-valued transactions per implementation without calling the arithmetic oracle.

- Combinational wrapper: 19 reset cases, all four elastic occupancy states covered, 620 full-trace stalled-clock checks.
- Registered wrapper: 18 reset cases, all six FSM phases covered, 1,467 full-trace stalled-clock checks.
- Reset is asserted away from both clock edges and immediately checked for asynchronous external flush, then held over three rising edges.
- Every reset is followed by a no-input drain to detect stale reappearing operations.
- Data/trace/flags remain stable through stalls and the eventual accepting clock.
- Accepted/completed counters, no output without a queued input, one-to-one ordered completion and post-drain no-duplicate behavior passed.
- Modulo-2^32 counter wrap follows the declared 32-bit register addition structurally; a 2^32-transfer simulation was not performed.

The directed protocol review is additional evidence, not a formal universal proof.

### Final artifact review

`independent_result_review.py <result-directory-or-result.json>` validates current source hashes, all result artifact hashes, immutable fixture hashes, original native products/outputs, all 25 actual DUT columns against both integer and observed C traces, the independent protocol source identities, and the post-fix C alias result. It independently recomputes every converter node from actual DUT raw products/sums and every standalone converter output using exact nearest-neighbor search. See `independent_result_review.json` for the exact result path/hash and counts.

## Separate conclusions

- **Functional:** candidate contract, individual conversion/FP32 nodes, flags and the two frozen native finite BF16 corpora pass the recorded component checks. Do not generalize source-native equivalence to arbitrary FP32 inputs, framework NaN payload conventions or full-model behavior.
- **Protocol:** reviewed simulations pass ready/valid ownership, full-trace stall stability, ordered completion, counter consistency and reset/drain checks for both wrappers.
- **Physical implementation:** source is synthesis-capable and actual emitted HardFloat is simulated. No synthesis, placement, STA, resource mapping or power evidence was produced. The six generic combinational ALU instances each contain add and multiply graphs before constant-op optimization; four multiply/two add operations per pair are not a post-synthesis resource count.
- **QoR:** no-stall simulation measures 2-cycle latency/1-cycle II for the two-slot wrapper and 9-cycle latency/10-cycle II for the registered-primitive FSM wrapper. These are simulated handshake cycles. A 10 ns testbench clock does not establish a 100 MHz implementation or an unchanged target frequency. Added conversion paths and observable trace registers may affect physical cost.
- **Isolation:** production arithmetic/emitter sources, frozen native expectations and numeric thresholds are unchanged relative to the review base. Documentation links and existing open-status metadata may change. A broad-test-generated coverage report mutation was identified and restored, rather than silently included.

Packing/store integration, byte enables, physical buffering, owner/DMA wiring, partial-RoPE layout and positions/coefficient generation, full-block producer policy and numerical acceptance, synthesis/PPA and whole-block MAC utilization remain open. U00.2/U01 completion is not claimed.
