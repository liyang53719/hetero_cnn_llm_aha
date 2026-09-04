# Operator primitive implementation plan and closure record

## Objective and claim boundary

Provide complete operator-primitive source coverage for Qwen2-1.5B,
Qwen3.5-35B-A3B and Qwen3.8-Flash-Next. The package reuses existing arithmetic
engines and adds missing state, selection, sparse-memory, multimodal and
micro-sequencing controllers. It does **not** claim emitted RTL, RTL simulation,
Command128 payload integration, DC synthesis or post-route closure.

## Closed source-level workstreams

1. **Frozen protocol, capability registry and no-fallback execution**
   - 48 high-level model-operator IDs;
   - explicit owner/opcode/variant/phase micro-ops;
   - non-empty sequence for every accepted operator;
   - source and terminal owner/opcode capability checks;
   - unknown operators and unsupported terminal bindings are errors.

2. **Terminal leaf closure**
   - composite `exp`, `sigmoid`, `softplus`, `SiLU`, `GELU` and signed sqrt are
     expanded into fixed-SFU add/multiply/compare/PWL/exp2/reciprocal leaves;
   - 58 terminal owner/opcode bindings have one declared provider each;
   - all three model sequences have zero unbound terminal opcodes.

3. **Gated DeltaNet and recurrent state**
   - causal/dilated convolution address walker;
   - four-pass external `M[head,K,V]` state walker;
   - Q/K L2 normalization, query scaling, beta sigmoid, softplus/exp decay,
     state decay, K readout, delta update, outer product and Q readout;
   - gated RMSNorm and output projection phases.

4. **MoE and speculative state**
   - stable sequential Top-K up to QSA K=512;
   - router softmax and selected-probability renormalization;
   - route dispatch, tagged OOO completion and deterministic reduction;
   - routed and shared SwiGLU expert phases plus shared-expert gate;
   - MTP verification and atomic commit/rollback generation.

5. **Qwen3.8 PLE/QSA/gated residual**
   - wraparound-XOR n-gram hash with iterative multiply/modulo;
   - sparse row/KV tagged gather and reorder;
   - block pooling, stable block Top-K and selected-token expansion;
   - four-branch group-RMS read/mix/injection write;
   - PLE projection, signed-sqrt gate and dilated depthwise convolution;
   - QSA index, summary, selection, sparse gather and sparse attention phases.

6. **Vision encoder**
   - Conv3D patch address generation and bias;
   - MRoPE T/H/W interleaving;
   - non-causal window layout and padding mask;
   - bilinear position interpolation with iterative multiply/divide;
   - LayerNorm, scaled attention, biased GELU MLP, patch merger/project,
     deepstack add and text-stream scatter.

7. **800 MHz migration**
   - active period is 1.25 ns;
   - existing architecture IDs are preserved;
   - historical 1 GHz evidence remains immutable;
   - new DC/STA runs must source `dc/operator_primitives_800mhz.tcl`;
   - 240 token/s is the frequency-scaled Qwen2 bring-up gate; 300 token/s
     remains the product target rather than a falsified 800 MHz guarantee.

## Sandbox closure evidence

The final source/semantic gate is:

```text
51 pytest tests passed
48 operator IDs
25 emitted-module catalog entries
58 terminal bindings
missing operators: 0 / 0 / 0
unbound terminal opcodes: 0 / 0 / 0
terminal micro-ops: 27 / 186 / 279
static source, shell syntax and git diff checks: PASS
```

The generated-RTL verifier checks catalog completeness, non-empty SystemVerilog,
module/endmodule structure, incomplete markers and SHA-256 provenance. It is
run by the local generation script after Chisel elaboration.
