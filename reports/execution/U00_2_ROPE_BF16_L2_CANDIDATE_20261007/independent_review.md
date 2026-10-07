# Independent review: opt-in BF16 RoPE SharedL2 consumer

## Decision

PASS for the bounded experimental head-transport gate. No remaining blocking defect was found in the reviewed RTL, transport checker, or final evidence. This is not approval to switch production arithmetic or close full-block acceptance.

The final primary run is `work/rope_bf16_l2_candidate_result_final/result.json`, status `PASS_EXPERIMENTAL_BF16_ROPE_SHARED_L2_HEAD_TRANSPORT`. `independent_final_binding.json` binds its result hash, every current source hash, and the independent checks below. The earlier primary attempt correctly rejected source drift and is not used for this acceptance.

## Defects found and resolved

1. Initial address admission used the full address encoding range. At ADDR_W=15 this allowed 2 MiB, while the default SharedL2 fabric implements only 1.5 MiB. The final RTL has an explicit fabric-capacity parameter, defaults to 24,576 beats at this width, rejects invalid capacities, and validates all complete byte ranges before any bus traffic. The wrapper forwards an explicit override.
2. Moving the legacy implementation under a generate branch broke the old payload test's hierarchical watchdog reference. The test now targets the legacy branch; existing stage/controller instantiations explicitly tie candidate-only inputs inactive.
3. The initial completion trace encoded flags in hexadecimal while the Python checker expected decimal. The final test emits decimal consistently, and focused parser tests now include nontrivial flag values.
4. The initial test updated its gate-driving cycle counter with a blocking assignment at the sampling edge. The final counter uses nonblocking assignment, removing the identified race.

## Independent execution

### Address admission and held requests

`run_independent_aperture.py` compiles the actual wrapper, candidate consumer, BF16 converters, and pinned generated HardFloat primitives. It runs two ADDR_W=15 configurations:

- Actual wrapper default, with capacity parameter omitted: 24,576 beats.
- Explicit smaller aperture: 8,192 beats.

Each configuration passes 15 invalid descriptors and six valid boundary checkpoints. Invalid cases cover source/coefficient/destination at the aperture end, ranges crossing the end, high-bit truncation, 64-bit overflow, and misalignment. They produce exactly one rejection completion, zero memory requests, and zero transaction counters. Valid cases include exact-last-valid source, coefficient and destination ranges, two-head boundaries, and the last legal unaligned BF16 destination. Each holds its first read request for nine blocked cycles while all caller configuration and start inputs change.

These auxiliary positives deliberately stop before first read acceptance. They prove admission, parameter propagation, descriptor capture, stall stability, and reset cleanup, not full payload execution. Both generated-RTL manifests and source stability are checked.

### Actual stores and frozen numerical expectations

`independent_store_review.py` independently decodes the final primary run's accepted bus writes. It does not import the new transport preparation, packet generator, record builder, or primary trace parser. It checks each physical address, byte-enable bit, masked data lane, completion count, and reconstructed output byte stream.

Results:

- 5,184 complete main transactions; 47,006 physical main-stream write beats.
- 2,686,976 enabled stored bytes.
- 335,872 rotated BF16 outputs exactly match immutable native NPZ outputs, including explicitly supplemental grouped replays.
- 1,007,616 nonrotated synthetic BF16 tail words exactly preserve source bits.
- Every even destination byte offset from 0 through 62 is covered.
- Source even/odd ordering and cos/sin lane order are rebound directly to the immutable historical input arrays.
- The real corpus exercises aggregate flags 0 and 1. Broader arithmetic special-value behavior remains supported by the separately accepted component gate; the present native replay is not evidence of universal framework special-value equivalence.

Unique historical coverage remains 163,840 real pairs and 327,680 native outputs. Supplemental replay is not counted as new unique source data. The 192-channel tails are explicitly synthetic, not recovered historical model outputs.

## RTL and test review

The final route uses a default-off generate parameter and a captured runtime policy byte. It accepts only one or two 256-element BF16 heads, rotary dimension 64, and exact 8/16 source beats. It loads the complete source and both coefficient beats before computation or stores. Split-half pairs use channels i and i+32; only the first 64 channels per head are overwritten with actual 16-bit candidate outputs. The remaining 192 channels are untouched raw bits, with no conversion flags.

Registered store address, data, and byte enables remain stable under backpressure. The packing equations were independently checked across all 64 combinations of head count and even byte offset. Every enabled byte maps bijectively to the expected tensor byte. The final completion follows the last accepted write, and counters measure accepted reads/writes and completed arithmetic pairs.

The main SystemVerilog test was inspected: it uses actual `shared_l2_fabric`, public host writes and readback, poisoned guards, protocol scoreboards, deliberate request/response/write stalls, busy-input mutation, 38 rejection cases, four coordinated reset cases, boundary positives, and overlapping stores. Its final run passes 5,184 main transactions, all 32 offsets, 38 rejections and four reset cases. The default-off mode passes two identity transactions through the original path. The legacy implementation body is byte-identical to commit 37df696; original FP32 pair arithmetic is unchanged.

The implementation is synthesizable in structure and elaborates with real generated primitives. Dynamic selection and whole-head storage can have significant hardware cost. This review and simulation do not establish mapped area, timing, SRAM inference, throughput under physical constraints, or power.

## Required limits

- The attached fabric's actual capacity must match the configured aperture; address width alone is insufficient.
- The supplied coefficient rows are conditional inputs. Position lookup, generation and cache semantics are not implemented or accepted here.
- Completion means the final SharedL2 write handshake, not DDR acknowledgement or tagged generic-SFU completion.
- Consumer and no-ID fabric response state reset together, for at least two rising clocks. Accepted stores survive reset; there is no atomic rollback or guarantee against stale responses after an uncoordinated reset.
- The inherited completion API is a one-cycle pulse without completion backpressure.
- This does not add generic SFU owner integration, Command128 acceptance, a complete Q8 tensor command, upstream QK Norm or packed-gate integration, full-block numerical acceptance, PPA acceptance, or MAC-utilization acceptance.

No production RTL was edited by this reviewer. Reviewer-created test sources, reproduction scripts, logs and JSON evidence are confined to this report directory; build artifacts are under `work/rope_bf16_l2_independent`.
