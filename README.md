# Heterogeneous CNN/LLM accelerator

```text
retained Gemmini INT8/CNN Matrix
+ Revision8B-B 512-lane BF16/FP32 Matrix
+ fixed-function Attention/Norm/SFU
+ legal Stanford AHA programmable sidecar
+ Sequence Memory/iDMA complex
```

The repository is main-only: no work branches or force-pushes without explicit user approval.

Closed at component/H3 scope: L5.1 Block128, L5.2 Matrix, L5.3 Controller/Block32 weight and standalone L5.4 one/two-lane candidates. Current critical work is the single-simulation full Attention E2 and measured SiLU lane selection.

Sandbox v7.0 adds deterministic Attention E2 packs, SiLU edge/stall coverage, quant K-tail scheduling RTL, 5,000 adversarial state transactions and an 11-case E3 matrix.

```bash
./scripts/sandbox_validate.sh
```

Verilator/VCS, CLN22UL, real iDMA/DDR, official model weights, llama.cpp/GGUF and post-route signoff remain local-agent gates.
