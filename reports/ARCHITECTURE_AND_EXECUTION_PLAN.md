# Canonical architecture and execution plan v6

## Audited remote state

At the v6 audit base, `main` is `7e18aa7b0c941c65cfa053d24d75757b99008511`; no newer local-agent commit exists. The latest accepted local evidence is `b8f8eaff6a323a6303a52b01db6a776ddbe9e406`: Block128 E1 passes and E4 fails timing at WNS -0.555804 ns.

## Serial local critical path

1. Validate FP32 raw/round pipelines.
2. Validate the Block128 `_rawpipe` candidate against the retained 132-vector/32-beat gate.
3. Require CLN22UL WNS >= 0 without timing exceptions.
4. Integrate the real 512-lane four-context BF16 array.
5. Continue blocked attention, fused SiLU, DMA overlap, and 28-layer q1024 closure.

## Sandbox work that is now closed at E0

- Archspec inheritance, validation, SRAM map, capability manifest, SystemVerilog parameter package and local-gate matrix.
- Qwen3.8 48-layer full-shape prefill/decode macro program with exact analytical MAC reconciliation.
- Deterministic mock backend partition, policy binding and bounded event scheduling.
- Sequence Memory two-level translation reference with TLB, leaf cache, generation rejection and COW-copy cost. MSHR and outstanding-request behavior remain a local E1/E3 item.

These results remove software/planning dependencies from L7/L8/L9, but do not replace RTL E1, integrated E3, official-weight traces or E4 physical evidence.

## Architecture boundary

Canonical `arch_v1.yaml` remains the accepted planning architecture. `arch_v2_qwen38_candidate.yaml` remains a candidate until official traces, per-backend E1, one-block/four-layer E2, integrated E3 and 1 GHz E4 all pass.
