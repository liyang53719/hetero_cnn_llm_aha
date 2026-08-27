# Model/operator support matrix v5

| Capability | Qwen3.5 | Qwen3.8 | Evidence | Next gate |
|---|---:|---:|---|---|
| Universal Block128 | full attention | sparse payload merge | canonical E1 PASS, E4 WNS -0.555804 | rawpipe E4 |
| Four-context BF16 accumulation | useful | required | RTL source + 1M-step E0 | L5.2 E1/E4 |
| Gated DeltaNet | 30 layers | 36 layers | recurrent/chunk E0 | L8.2 |
| QSA append summaries/Top-512 | no | yes | 200-case exact E0 | L8.3 |
| Sparse page coalesce/restore | no | yes | executable E0 | L7/L8.3 |
| Four-branch Gated Residual | no | yes | executable tiny E0 + liveness | L8.4 |
| PLE random rows/dilated conv | no | yes | E0 + synthetic cache DSE | L8.4 |
| Routed/shared MoE | top-8/256 | top-10/512 | E0 + expert-cache DSE | L8.5 |
| Full-state MTP transaction | yes | yes | 1000-case E0 | L7/L8.5 |
| W4 expert path | target | required | analytical/synthetic DSE | L6/L8.5 |
| Official-weight text | no | no | not claimed | L8.1-L8.6 |
| Vision | present | present | unsupported | outside scope |
