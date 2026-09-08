# Transport batching checkpoint

This work follows main@d01e2e10571dd3e95810a5e9e3610b9b3d8aba38. The development target remains >=50% useful-MAC utilization over a complete request. No component result changes that requirement.

Implemented in Chisel and being sealed for publication:

- Bounded Dense output burst writes through the SAME retained iDMA backend. Success follows the external write response and backend completion.
- Streaming read forwarding for intermediate payload beats, with the final beat withheld until backend completion. Metadata reads retain commit-before-response behavior. Late errors abort the owner; partial internal work never publishes a successful tensor.
- Existing native BF16 weights and cross-token weight reuse are retained, as are the original Host command and numerical contracts.

Actual sandbox verification already completed:

- Native-weight Dense baseline: 13 cases, 11 numerical cases, two error/reset cases, 216128 FP32 outputs; bit differences 0.
- Burst-write Dense: same 13 cases and all 216128 outputs byte-identical to the baseline.
- Real-iDMA burst-write transport: 15 cases including invalid boundaries, write errors and reset recovery.
- Commit-tail read transport: 11 streaming cases including three late-error/reset cases, plus a non-streaming metadata-read case.

These are component tests, NOT full real16 two-layer or 50% performance acceptance. Full Host integration is still under verification. All previous failed compilation attempts and numerical outputs are retained. Source changes are limited to Chisel and test/build software, not hand-edited RTL.
