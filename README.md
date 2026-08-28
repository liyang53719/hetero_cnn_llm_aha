# Heterogeneous CNN/LLM accelerator

```text
retained Gemmini INT8/CNN Matrix
+ clean-room BF16/FP32 LLM Matrix
+ fixed-function Attention/Norm/SFU
+ legal Stanford AHA sidecar
+ paged KV / Sequence Memory Complex
```

Current audited L5 state:

```text
L5.1 Block128 E1/E4       ACCEPTED; component WNS +0.0000136495 ns
L5.2 512-lane E1          ACCEPTED; 4 contexts, 1M dependent steps, II=1
L5.2 Revision-6 lane E4   FAIL: -0.034333 / -0.0371628 ns
L5.2 Revision 7           APPROVED_WITH_GATES; local DC/equivalence/H3 pending
```

Revision 7 remaps one reusable context lane from pinned emitter-generated SystemVerilog plus unchanged handwritten lane RTL. It permits DC to optimize through the accumulator mux and HardFloat Pre, but does not permit RTL edits, retiming, another context/cycle, reduced frequency, or timing exceptions.

Run sandbox gates:

```bash
./scripts/sandbox_validate.sh
python3 scripts/validate_l5_revision7_contract.py
python3 scripts/run_l5_blocked_attention_cycle_e0.py
```

Run local Revision-7 gates:

```bash
./scripts/run_l5_matrix_context_revision7.sh lane
./scripts/run_l5_matrix_context_revision7.sh equiv
./scripts/run_l5_matrix_context_revision7.sh e1
./scripts/run_l5_matrix_context_revision7.sh top
./scripts/run_l5_matrix_context_revision7.sh e1
python3 scripts/summarize_l5_revision7.py
```

L5.2 closes only after single-lane E4, mapped equivalence, real 512-lane E1, and structural H3 E4 all pass. `arch_v2_qwen38_candidate.yaml` remains non-canonical; shape/cycle references are not official-weight, E3, or PPA claims.
