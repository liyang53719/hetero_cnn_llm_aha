# Heterogeneous CNN/LLM accelerator

```text
retained Gemmini INT8/CNN Matrix
+ Revision8B-B 512-lane BF16/FP32 Matrix
+ fixed-function Attention/Norm/SFU
+ legal Stanford AHA programmable sidecar
+ Sequence Memory/iDMA complex
```

The repository is main-only: no work branches or force-pushes without explicit user approval.

Accepted on the Qwen2 path: Block128, Revision8B-B Matrix, full Attention E2/stress, selected one-lane SiLU, balanced 8×8 Attention SFU E1/E4, composed real-RTL E3 at 321.869395 token/s, and a 28-layer count/trace E3 at 320.791599 token/s. Official-reference checkpoints, 160 sampled LM-head columns and a reduced four-layer cross-RTL replay also pass.

The continuous 28-layer payload numerical RTL gate remains open. L10 early PPA runs in parallel; component or hierarchical positive WNS is not post-route/PVT/OCV signoff.

```bash
./scripts/sandbox_validate.sh
cat reports/execution/LOCAL_AGENT_HANDOFF_V78.md
```

Local-only gates include hierarchy-preserving integrated synthesis, SRAM macro replacement, full-payload replay, post-route/PVT/SAIF, AHA/CNN, low-bit RTL, production Sequence Memory, official Qwen3.5/Flash-Next backends and real llama.cpp/GGUF.
