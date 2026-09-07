# Qwen2 Host21：跨 tile、重定位、生命周期和多层回归

## 冻结身份和范围

完整 CI 被测源码：`f0883276d626e189fd04806521c830df11961a43`。
实际 GitHub Actions：`34105607211`，tiny 与 real-cross 两个 job 均成功。
两组完整证据均已包含在 `0515b678d1cca3ff90e49e9003a263274d6fb5d5`。

- `reports/execution/OWNER_REGRESSION_f0883276d626_tiny/`
- `reports/execution/OWNER_REGRESSION_f0883276d626_real-cross/`

全程仍为 DDR Host Command128/typed descriptor → 原 Matrix/SFU/KV owner → 同一 pinned iDMA → 写回确认。没有 BlockLaunch 旁路、golden 中间态注入或 Host 层间拷贝。硬件设计源为 Chisel；这轮没有修改保留 RTL 或手工修改生成电路，也没有为测试增加第二套 MAC/DMA。

## 已完成回归

| 场景 | H / FFN | tokens / layers | Host commands | 全部 FP32 输出 |
|---|---|---|---:|---:|
| 基线跨 tile | 64 / 128 | 17 / 1 | 21 | 21,216 |
| 独立地址交换及重定位 | 64 / 128 | 32 / 1 | 21 | 39,936 |
| 第三个 tile 尾部 | 64 / 128 | 33 / 1 | 21 | 41,184 |
| 超过 48-bit 地址范围的重定位 | 64 / 128 | 33 / 1 | 21 | 41,184 |
| 两层，不同权重 | 64 / 128 | 17 / 2 | 42 | 42,432 |
| 三层，不同权重 | 64 / 128 | 33 / 3 | 63 | 123,552 |
| 真实维度及重定位 | 1536 / 8960 | 17 / 1 | 21 | 748,544 |

上述逐元素比较全部 bit-exact。真实维度 real17 为 130,195,365 cycles、795,946,752 useful MACs、1,511,522,304 executed MACs。这是合成权重、固定 BF16/FP32 配方的单 block 数值执行，不是整网 prefill 性能。

第二请求：tiny17、同一个 DUT、不复位，改变输入和权重并切换 epoch。两次请求共 42 commands / 42,432 个值通过；旧 request 的 tensor 有效状态不会保留为新 request 的合法输入。

故障恢复：42 个 metadata 故障覆盖每个 PC 的 command/descriptor 读取；57 个 payload 故障覆盖 19 个实际 owner 的读、首写、末写。每个故障均检查失败 PC、成功 completion 前缀、reset-required、不启动消费者；随后复位同一个 DUT，完整 21-command 请求恢复通过。QK/Softmax 的两个逻辑命令不单独产生 payload，不能伪造其不存在的 payload fault site。

## 多层连续性和额外跨层故障

两层与三层用一个 Host launch，不在层间 reset。后一层 X 的 descriptor 与前一层实际 Y 地址相同；每层有不同权重和独立 KV 输出区。每个输出都从 DUT 的 DDR 写回读取；CPU reference 仅比较，不提供下游输入。

沙箱又在三层 tiny33 图的全局 PC 21、32、33、41、42、62 注入六种定向故障，覆盖跨层入口、融合 Attention、层间 Y 末写和最终 Y 末写。每次均完整恢复到 63 commands / 57 jobs / 123,552 个输出。包括失败前已完成前缀，共独立重读 1,180,608 行 CSV；六份恢复后的实际输出与 CI 的三层正向输出完全一致。

新增测试入口为 `tests/host_owner_stack_recovery.cpp` 和 `scripts/run_owner_stack_recovery.py`。这六项为沙箱实际执行，不冒充原 CI job 的测试。它们的原始日志、全部输出、CSV 在本轮交付 ZIP 中；Git 中保存源码及带输出哈希的独立复核摘要。

## 独立复核与证据保护

沙箱实际执行 42 项 Chisel DUT 单测全部通过；另在两层/三层 metadata 上各复跑同一组 7 项 decoder 测试。tiny 的所有正向、第二请求和 99 项故障恢复也独立运行，3,144 份 actual tensor、3,300,960 个 FP32 值与 CI 对应场景逐字一致。场景按 mode + fault_pc 对应，不用两种执行顺序下不同的目录编号匹配。

完整 CI 二进制、CSV、manifest 另经只读复核。compiled library 的历史摘要保留为 provenance；只读复核不会声称缺失的 CI 编译库又被重新校验或重新仿真。

本轮还修复两个 Python launcher 的 CLI：原来拒绝已经存在的输出目录时，会把该目录中的旧 `gate.exit=0` 改成 1。现在拒绝操作不写旧目录。10 项新测试在普通与 `python -O` 均通过；失败或缺少 gate 不能计作 PASS。既有 proof 的 source 校验仅允许这一个可逆的 CLI 单行更改，并重建完整旧字节流核对原 SHA，不能借此忽略 DUT、测试、配方、容差或其他代码变化。

## 执行 agent：只复核和执行，不改代码

只读复核不需要模拟器、编译库或旧 CI 绝对路径。使用当前 main，选择新的输出目录：

```bash
OUT="$PWD/work/rechecks/owner_$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$OUT"
for PROFILE in tiny real-cross; do
  python3 chisel/continuous_prefill/scripts/recheck_published_owner_regression.py \
    --repo "$PWD" \
    --evidence "reports/execution/OWNER_REGRESSION_f0883276d626_${PROFILE}" \
    --source f0883276d626e189fd04806521c830df11961a43 \
    --output "$OUT/${PROFILE}.json"
done
```

重新执行完整两档回归，沿用已锁定的 IDMA_EXPORT、Java/Verilator/HardFloat 环境：

```bash
bash chisel/continuous_prefill/scripts/run_owner_regression_gate.sh tiny /absolute/new/tiny
bash chisel/continuous_prefill/scripts/run_owner_regression_gate.sh real-cross /absolute/new/real_cross
```

额外六项跨层恢复使用前一条 tiny 回归保留的原 DUT 编译库和三层 fixture。VERILATOR_ROOT 指向该环境的真实 runtime：

```bash
python3 chisel/continuous_prefill/scripts/run_owner_stack_recovery.py \
  --repo "$PWD" --build /absolute/new/tiny/base17 \
  --fixture /absolute/new/tiny/layers3_33/fixture --output /absolute/new/cross_layer_faults
```

成功必须有零退出码和对应 PASS、完整命令/数值计数。缺依赖为 BLOCKED；异常只保留目录并返回原始错误。不要改阈值，不要注入参考 tensor，不要删除 checkpoint/日志，不要修改 Chisel 或 RTL。

## 尚未闭合及下一关

这里不是官方权重质量、多请求持久 KV、真实尺寸多层、q1024 全网络或 800 MHz DC。当前具体 frontend 的 64-command 容量可覆盖三层 63 条命令，不能直接宣称可接收 28 层 588 条命令。

下一关保持共同生产路径：真实尺寸两层 real16 的 42-command 图（不同权重、实际 Y→X），随后真实尺寸 32/33-token 与更长序列。在扩展完整 28 层前，由开发侧完成命令容量/分页、tensor 生命周期、权重加载与官方数值合同；不得回到自动 BlockLaunch。执行 agent 仍不承担编码。
