# Heterogeneous CNN/LLM accelerator

```text
retained Gemmini INT8/CNN Matrix
+ Revision8B-B 512-lane BF16/FP32 Matrix
+ fixed-function Attention/Norm/SFU
+ Stanford AHA programmable sidecar
+ Sequence Memory/iDMA complex
```

The repository is main-only: no work branches or force-pushes without explicit user approval.

Qwen2 q1024 performance, component RTL, sampled/reduced RTL and the continuous llama.cpp HETERO backend route pass. `main@11483e8` receives the original 958-node graph as one split, binds 338 canonical GGUF payloads and runs 28 layers with zero scheduler fallback. The backend is currently host software emulation behind a GGML backend: it uses CPU buffers, a monolithic C++ submission and inter-stage files. It is not Command128 RTL/device execution or all-row RTL closure.

Current critical work:

```text
full-logit metrics
-> one-layer 21-command real RTL/device transport canary
-> all 588 commands with Matrix/SFU/KV counts 252/308/28
-> non-host buffers/no file staging
-> functional SRAM replacement and post-route/PVT/SAIF
```

```bash
./scripts/sandbox_validate.sh
cat reports/execution/LOCAL_AGENT_HANDOFF_V719.md
```
