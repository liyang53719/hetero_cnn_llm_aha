# Implementation status v4

## Sandbox-completed

| Item | Status | Evidence |
|---|---|---|
| Canonical architecture/control plane | PASS | `config/control_plane.json`, canonical plan/stages |
| Descriptor v3 and explicit capability split | PASS | records 0x04, 0x13-0x19, 0x32-0x35 |
| Universal block-128 M/L/O | PASS E0/source | 132 vectors, C++20 reference, RTL source |
| Matrix context protocol seed | PASS source | parameterized scoreboard; real array integration local |
| Paged KV v3 | PASS E0 | prefix, COW, generation, one-million-token addressing |
| Qwen3.5 common GDN/MoE/MTP operators | PASS E0 | executable references |
| Qwen3.8 four-branch GR | PASS E0 | full low-rank read and injection write |
| Qwen3.8 PLE | PASS E0 | n-gram hash, lazy lookup, projection, gate, dilated conv state |
| Qwen3.8 GDN recurrent | PASS E0 | persistent state and causal conv |
| Qwen3.8 GDN chunk prefill | PASS E0 | 100 random chunk/recurrent comparisons |
| Qwen3.8 QSA sparse attention | PASS E0 | index cache, block top-k, sparse online Softmax/PV, output gate |
| Qwen3.8 routed/shared MoE | PASS E0 | numerical expert execution and route weights |
| Qwen3.8 MTP state transaction | PASS E0 | accepted-prefix commit and rejected-state rollback |
| Qwen3.8 reduced stateful text path | PASS E0 | prefill/decode exact, frozen hashes |
| Hardware micro-op schedule | PASS E0 | all executed text ops have an owner |
| Python regression | PASS | 81 tests |

## Local dependencies

| Evidence | State |
|---|---|
| Verilator/VCS Block128 E1 | WAIT_LOCAL_AGENT_PUSH |
| 512-lane Matrix contexts E1/E4 | WAIT_LOCAL_AGENT_PUSH |
| Qwen3.8 official-weight trace | WAIT_LOCAL_AGENT_PUSH |
| GDN/QSA/GR/PLE/MoE/MTP RTL | WAIT_LOCAL_AGENT_PUSH |
| llama.cpp backend | WAIT_LOCAL_AGENT_PUSH |
| Integrated DDR/cycle E3 | WAIT_LOCAL_AGENT_PUSH |
| 22nm DC/STA/SAIF E4 | WAIT_LOCAL_AGENT_PUSH |

## Deliberate non-claims

- The reduced Qwen3.8 model is an architectural E0 reference, not the official
  125B model and not a quality benchmark.
- Descriptor recognition is not backend execution.
- Existing cycle reports are not promoted to E3 unless real queues, DDR and
  engine completion drive the trace.
- Vision remains unsupported.
- No PPA or throughput claim is made from the sandbox.
