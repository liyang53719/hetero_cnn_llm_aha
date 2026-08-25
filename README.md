# Heterogeneous CNN/LLM Accelerator Exploration Harness

本工程是 `Matrix Engine + CGRA/SFU + KV Memory Engine` 的可执行架构基线。它遵循：

```text
先复现第三方原版
→ 用外部 wrapper 集成
→ 最小修改复用
→ 只对缺失能力新写 RTL
```

本工程原创部分采用 Apache-2.0；第三方源代码不包含在交付包内。Matrix baseline 指向 Gemmini；CGRA/SFU baseline 指向 Stanford AHA；DMA/AXI 指向 PULP iDMA/axi/common_cells；IMAX3-LLM 仅作 llama.cpp offload 参考；KV control/data path 为 clean-room 新实现。

## 已包含

- `configs/arch_v0.yaml`：1 GHz、4 MiB SRAM、32×64 logical matrix、4×4 CGRA/SFU、paged KV 配置。
- `spec/command_isa.yaml`：128-bit command envelope；`spec/descriptor_schema.yaml`：可链式 typed descriptor 合同。
- `src/heteronpu/`：INT8/BF16/W4 functional model、CGRA/SFU、paged KV、CNN/LLM workload 和 cycle scheduler。
- `examples/` + `artifacts/segments/`：CNN、LLM prefill/decode segment 描述及编译后的 128-bit command binaries。
- `tests/`：command、descriptor、dtype、matrix、SFU、KV、workload、scheduler tests。
- `rtl/`：clean-room ready/valid FIFO、INT8 matrix tile、vector SFU、small paged KV contract、command shell，以及 L5/L6 contract scoreboard/engine adapters/shared-L2 fabric。
- `tb/`：六个 SystemVerilog contract/integration testbench，供本地 Icarus/Verilator 使用。
- `cpp/reference_smoke.cpp`：独立 C++17 reference smoke。
- `scripts/`：sandbox validation、随机参考扫掠、upstream clone/reproduction、open RTL、DC 22nm scripts。
- `reports/ARCHITECTURE_AND_EXECUTION_PLAN.md`：完整架构与分阶段计划。
- `local_agent/AGENT_EXECUTION_GUIDE.md`：本地 agent 执行合同。

## 沙箱复现

```bash
cd hetero_cnn_llm_aha
PYTHONPATH=src pytest -q
PYTHONPATH=src python -m heteronpu --config configs/arch_v0.yaml
PYTHONPATH=src python scripts/generate_reports.py
PYTHONPATH=src python scripts/randomized_reference_sweep.py
python scripts/rtl_static_check.py rtl --output reports/rtl_static_check.json
/usr/bin/g++ -std=c++17 -O2 -Wall -Wextra -Werror cpp/reference_smoke.cpp -o /tmp/heteronpu_ref
/tmp/heteronpu_ref
taskset -c 8-25 ./scripts/run_open_rtl.sh
taskset -c 8-25 python scripts/l56_contract_validate.py
```

或运行：

```bash
./scripts/sandbox_validate.sh
```

## 证据边界

`reports/final_validation.json` 只记录实际在当前环境运行的项目。分析型 cycle model 不是 RTL measured cycle；structural RTL checker 不是 SystemVerilog compiler；W4 native 4096 MAC/cycle 是未来目标，不是已综合结论。

本工程的编译/测试命令限定为 `taskset -c 8-25`。当前主机在线 CPU 为 0-23，因此 Linux 实际生效亲和力为 8-23（24-25 不存在）；在有这些核心的机器上则使用完整 8-25。当前本地第一版 contract RTL 已可由 Icarus 编译并运行三个 block testbench；Verilator、upstream Gemmini/AHA 和 22nm DC 仍是后续门禁。
