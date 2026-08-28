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
L5.1 Block128 E1/E4       accepted; WNS +0.0000136495 ns, zero margin
L5.2 512-lane E1          accepted; 4 contexts, 1M dependent steps, II=1
Revision-7 lane/equiv     pass
Revision-7 structural H3 fail: WNS -0.926028 ns
Revision 8A candidate     sandbox E0/source-ready; local E1/E4 required
```

Revision 8A removes the completion-handshake-to-HardFloat-Pre data path. The
four context banks become the output-stage registers while architectural
completion remains on the original output handshake. Candidate files remain
under `rtl/matrix/candidates/rev8/` until all gates pass.

Run sandbox gates:

```bash
./scripts/sandbox_validate.sh
python3 scripts/validate_l5_revision8a_contract.py --operations 100000
```

Run local Revision 8A gates:

```bash
./scripts/run_l5_matrix_context_revision8a.sh compare
./scripts/run_l5_matrix_context_revision8a.sh e1
./scripts/run_l5_matrix_context_revision8a.sh adversarial
./scripts/run_l5_matrix_context_revision8a.sh lane
./scripts/run_l5_matrix_context_revision8a.sh equiv
./scripts/run_l5_matrix_context_revision8a.sh cluster
./scripts/run_l5_matrix_context_revision8a.sh front
./scripts/run_l5_matrix_context_revision8a.sh top
./scripts/run_l5_matrix_context_revision8a.sh e1
./scripts/run_l5_matrix_context_revision8a.sh adversarial
python3 scripts/summarize_l5_revision8a.py
```

Or run the same ordered sequence with:

```bash
./scripts/run_l5_matrix_context_revision8a.sh all
```

L5.2 remains open until every Revision 8A E1/equivalence/E4 gate passes. The
Qwen3.8 Archspec candidate remains non-canonical; shape/cycle models are not
official-weight execution, integrated E3 or physical signoff.
