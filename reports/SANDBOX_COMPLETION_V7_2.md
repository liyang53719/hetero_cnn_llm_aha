# Sandbox completion v7.2

All six previously listed sandbox work packages are closed at their honest boundary. SiLU `Q4.12==0` uses the local `gate/2` limit and passed rerun E1/DC. The remaining packages are deterministic E0 or source-ready contracts.

| Work package | Result |
|---|---|
| Attention multi-seed/adversarial | 4 random seeds, 7 adversarial patterns, max abs `4.7683716e-7` |
| Quant integrated frontend | 8,000 cases, 2-deep block/beat FIFOs, tag/scale alignment PASS |
| State multi-slot/COW/dirty | 10,000 transactions, 8 slots, 907 same-cycle refcount/COW cases, zero leak |
| Tiny Qwen3.8 multilayer trace | 4 layers, 216 nodes, prefill/decode exact match, fallback 0 |
| Service-curve importer | good `333.904 t/s` PASS_REVIEW; degraded `266.439 t/s` reopens architecture |

These do not replace RTL elaboration/E1, full Attention E2, real iDMA/DDR E3, official weights or post-route signoff.
