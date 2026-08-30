# Sandbox continuation v6.8

## Audit

No commit newer than `e87eb9763ddec26ed67a92980e7487452519103b`
was present when this work started. The latest accepted local-agent evidence
remains `eba24625350d14fe3f9d760929736dcf5872fabd`, which closed L5.2 at the
component/H3 boundary. L5.3 and L5.4 remain open.

## New sandbox closures

### Unified quant operand frontend

- FP16, Q8_0, Q6_K and Q3_K emit 16-value beats.
- Integer beats carry signed operands, one FP16 block scale and one signed
  subscale; FP16 uses the shared floating multiplier mode.
- 1,000 random cases per format pass with maximum dot difference
  `4.547473508864641e-13`.
- A SystemVerilog group decoder source contract is included. No separate
  format-specific multiplier array is permitted.

### State commit protocol

- Ten state domains, out-of-order acknowledgements, accepted-prefix commit,
  last-write-wins, epoch advancement and stale-response suppression.
- 1,000 random transactions pass with zero protocol errors.
- Source-ready epoch, stale-filter, commit-barrier and dirty-domain modules are
  included, but have not been elaborated in this sandbox.

### Trace and software boundary

- Deterministic official tensor/state trace schema and offline replayer pass.
- Versioned GGML node/tensor adapter passes and keeps unsupported nodes as
  explicit CPU fallback without model-name conditionals.

### L5.5 sensitivity

- Baseline remains `338.251729` t/s.
- 32,000 sensitivity points: 30,739 pass and 1,261 fail.
- Review scenario: `329.828958` t/s.
- Measured pre-route projection below 315 t/s triggers a performance/architecture
  review rather than a 300 t/s signoff claim.

## Evidence boundary

This work is E0/source-ready only. Verilator/VCS, pinned llama.cpp parity,
official model traces, iDMA/DDR E3 and post-route/PVT/SAIF remain local gates.
