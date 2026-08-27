# Canonical L0-L11 stage namespace

There is one stage namespace only; the former internal L0-L13 remapping is
retired.

| Stage | Scope |
|---|---|
| L0 | Control plane, provenance and sandbox regression |
| L1 | Unmodified upstream baselines |
| L2 | Wrapper-only integration |
| L3 | Shared SRAM, streams, events and fabric |
| L4 | CNN path and legal AHA sidecar |
| L5 | Qwen2 BF16 long-context 300 token/s closure |
| L6 | W8/W4/KV-INT8 quantified path |
| L7 | Production paged KV and continuous batching |
| L8 | Qwen3.5/Qwen3.8 hybrid text backends |
| L9 | llama.cpp automatic backend |
| L10 | SRAM/DC/STA/SAIF physical closure |
| L11 | Fixed-environment architecture sweep and signoff |

Current serial stage is L5. Sandbox L8 E0 work may proceed in parallel but
cannot change the global next action or claim E1-E4 evidence.
