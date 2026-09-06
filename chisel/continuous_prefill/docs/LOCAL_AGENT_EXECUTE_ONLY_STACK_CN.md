# 本地 Agent：只复核和执行，不修改代码

## 职责边界

本地 Agent 不修改 Chisel、RTL、C++ oracle、Python 校验器、位宽、模型尺寸或误差阈值；不拼接新仿真路径，不自行修复失败。任何失败都保留原输出目录、命令、commit 和首个错误，由开发侧继续修复。

所有硬件源修改只在 Chisel。生成的 SystemVerilog 不得手工修改。不得删除旧 checkpoint、源码工件或失败日志；不得 force-push 或创建新开发分支。

## 先复核已提交状态

在干净 checkout 中使用 `main`，执行 `git pull --ff-only`。检查 GitHub Actions 的 `chisel-qwen2-developer-gate` 工作流，以及 `reports/execution/DEVELOPER_STACK_CI_<被测SHA>.json`。

报告必须区分以下三项：tiny 四层 17-token、真实尺寸两层 1-token、真实尺寸单层 16-token。没有完成收据、工作流失败、源码发生变化时，不能沿用 PASS。真实尺寸要求 hidden=1536、FFN=8960；tiny 不得作为真实尺寸替代。

检查 `tested_source_commit` 到当前 checkout 的差异。Chisel、oracle 或测试运行脚本有变化时，必须在新输出目录重跑，不仅检查报告中的布尔字段。

## 固定执行命令

### 1. 完整连续 tiny 四层

```bash
bash chisel/continuous_prefill/scripts/run_qwen2_stack.sh \
  tiny /absolute/new/output/qwen2_tiny4_t17 17 4
```

验收：4 层、60 阶段、71,808 个 FP32 值、bit_diffs=0、Host 中间态写入=0；后层实际读取前层写回的 hidden。不是完整网络，不是官方权重测试。

### 2. 真实尺寸完整单层与多层

```bash
bash chisel/continuous_prefill/scripts/run_qwen2_stack.sh \
  real /absolute/new/output/qwen2_real1_t16 16 1

bash chisel/continuous_prefill/scripts/run_qwen2_stack.sh \
  real /absolute/new/output/qwen2_real2_t1 1 2
```

验收：单层 16-token 检查 663,552 个 FP32 值；两层 1-token 检查 82,944 个。必须完整执行全部阶段，不能停在 Gate/Up 就报告完成。结果仍是合成权重、standalone 功能数据通路，不能冒称原 512-MAC/iDMA 系统已完成。

### 3. 真实权重输入

本地提供已有、来源可核验的 `Qwen/Qwen2-1.5B` Safetensors checkpoint 目录、原始 token ID JSON 文件和完整 upstream revision。checkpoint 应为未改写的官方快照；保存获取记录和文件哈希。当前脚本不接受 GGUF，不能通过改扩展名或猜测 Q/K 排列绕过。

```bash
python3 chisel/continuous_prefill/scripts/run_packed_qwen2_stack.py \
  --checkpoint "$QWEN2_CHECKPOINT" \
  --token-ids "$QWEN2_TOKEN_IDS_JSON" \
  --revision "$QWEN2_REVISION" \
  --layers 2 \
  --out /absolute/new/output/qwen2_checkpoint_stack
```

该脚本自动生成 Chisel RTL、按层打包权重和初始 hidden、编译仿真并逐阶段比较。中间区必须保持 NaN poison；不加载 reference hidden。成功标签是 `PASS_PACKED_CHECKPOINT_HARDWARE_RECIPE`，不是官方 Transformers 前向通过。

缺少权重、Java/sbt/Verilator 等环境时报告 BLOCKED 和具体缺失项，不修改实现，也不换 tiny 或随机权重冒充真实输入。

### 4. 独立 FP32 方程参考

```bash
python3 chisel/continuous_prefill/scripts/compare_qwen2_stack_reference.py \
  --checkpoint "$QWEN2_CHECKPOINT" \
  --packed-run-dir /absolute/new/output/qwen2_checkpoint_stack \
  --out /absolute/new/output/qwen2_checkpoint_fp32_reference
```

需要 NumPy 和 PyTorch。该参考是同一 checkpoint 的 FP32 方程实现，明确不是官方 Transformers forward。三个误差门槛写在已提交源码中，本地 Agent 不修改。失败时返回结果和日志，等待开发侧诊断。

## 不交给本地 Agent 编码的工作

以下仍属于开发侧，在对应实现和验证门禁完成之前不得转为本地执行任务：原 512 个有效 MAC lane 的完整调度、原 Command128 全图入口、实际 pinned-iDMA backend 适配、GGUF 格式和坐标映射签核、Qwen3.5/Qwen3.8 完整连续执行以及生产 SRAM 宏映射。

已有 direct AXI 接口不能标为 pinned-iDMA；物理实例化 512-lane 阵列而只使用 16 个结果也不能标为 512-lane 利用率通过。

## 回传内容

只回传：当前 commit、完整命令、退出码、RESULT.json、源码/生成文件/权重哈希、编译和仿真日志、首个失败阶段。不得用 launch 记录替代完成记录，不得删除失败记录后重用相同目录。

q1024 的最终目标仍需 28 层 Qwen2 连续执行、最后 Norm/LM head 的完整 logits，以及同一请求内的周期/MAC/DDR 计数。单 block 或本文件中任一测试通过都不能提前升级为整网 q1024 完成。
