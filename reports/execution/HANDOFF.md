# Local-agent handoff v4

The repository contains executable E0 references for the Qwen3.8 text path and
remains globally blocked at L5.1 for real RTL/physical evidence.

Sandbox gates:

```text
19 Python tests                               PASS
132 Block128 M/L/O vectors                    PASS
independent C++20 merge reference             PASS
Qwen3.8 tiny stateful text prefill/decode     exact match
GDN chunk vs recurrent, 100 random cases      PASS
```

Canonical local action:

```bash
PYTHONPATH=src pytest -q
PYTHONPATH=src python3 scripts/run_qwen38_text_e0.py
PYTHONPATH=src python3 scripts/run_gdn_chunk_e0.py
PYTHONPATH=src python3 scripts/generate_block128_vectors.py
HETERONPU_FP_FILELIST=<filelist> ./scripts/run_l5_block128_merge.sh
```

Attach actual RTL logs and early DC reports. Update the result JSON,
`MASTER_LEDGER.json`, `NEXT_ACTION.json` and this handoff in one recoverable
main-branch commit. Records 0x13-0x19 remain `status=4` until each backend has
its own E1/E2 closure.

Parallel L8.1 work is permitted: use the frozen Qwen3.8 revision to generate
official tensor/node traces for GDN, QSA, GR, PLE, MoE and MTP. Trace generation
must not be reported as RTL support.
