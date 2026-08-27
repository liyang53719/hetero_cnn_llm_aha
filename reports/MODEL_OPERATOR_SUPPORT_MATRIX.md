# Model/operator support matrix v4

| Capability | Qwen3.5 | Qwen3.8-Flash-Next | Sandbox level | Local gate |
|---|---:|---:|---|---|
| BF16 GEMM / RMSNorm / partial RoPE / GQA | yes | yes | RTL primitives, not integrated | E1/E2 stream integration |
| Universal block-128 attention | 10 full-attn layers | sparse selected payload | RTL source + E0 vectors | L5.1/L8.3 |
| Gated DeltaNet recurrent decode | 30 layers | 36 layers | **Executable E0** | L8.2 E1/E2 |
| Gated DeltaNet chunk prefill | yes | yes | **Executable E0; 100 random parity cases PASS** | L8.2 E1/E2 |
| Causal Conv1D state | conv4 | conv4 | **Executable E0** | L8.2 |
| MoE top-k routing and expert batching | 256 / top-8 | 512 / top-10 | **Executable E0** | L8.5 |
| Routed expert + shared expert numerical execution | yes | yes | **Executable E0** | L8.5 grouped GEMM/cache |
| MoE dispatch/cache | yes | yes | compiler schedule only | L8.5 |
| QSA compressed-block indexer | no | yes | **Executable E0** | L8.3 |
| Sparse causal QK / online Softmax / PV | no | yes | **Executable E0 tiny text path** | L8.3 |
| Attention sigmoid output gate | no | yes | **Executable E0** | L8.3 |
| Four-branch Gated Residual low-rank read/write | no | yes | **Executable E0** | L8.4 |
| PLE n-gram hash and lazy embedding lookup | no | yes | **Executable E0** | L8.4 transport/cache |
| PLE signed-sqrt gate and dilated depthwise conv | no | yes | **Executable E0** | L8.4 |
| MTP verify and transactional state rollback | yes | yes | **Executable E0** | L8.5 |
| Stateful reduced text path | no | yes | **Executable E0, prefill/decode exact** | official trace + L8.2-L8.6 |
| Official-weight text model | not yet | not yet | unsupported claim | L8.1-L8.6 |
| Vision encoder | present | present | unsupported | outside current scope |

`executable E0` means the numerical/state path runs in the sandbox. It does not
mean that descriptor records 0x13-0x19 are executable RTL; the capability
decoder continues to return `unsupported_policy` until each local backend closes.
