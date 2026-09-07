# Qwen2 real16 双层 Host 命令链：完成与执行说明

## 冻结结果

实际被测源码：`9f06249ca11fcee35c0cd4d3e51c0b2fe0dfec30`。
真实硬件仿真：GitHub Actions run `34122096771` / job `101742253297`，完整成功。
完整原始证据提交：`0721e1d2bfb2e6e34491b2baef6b81cf7fdd7ef3`。
证据目录：`reports/execution/REAL16_TWO_LAYER_9f06249ca11f/`。

本次已通过真实尺寸 16 tokens、hidden=1536、FFN=8960、12 Q heads、2 KV heads、head_dim=128 的两个不同权重 decoder block。一个 Host launch 读取 42 条原始 opcode Command128 和 430 个 typed descriptor，执行 38 个物理 owner 作业。QK/Softmax/PV 三命令先完整校验再流式融合，两个 layer 各减少两个物理作业；不是缺失命令。

层间直接使用同一 DDR 地址：`l0_y == l1_x == 0x34ae30c40`。l1_x 没有独立 Host 初始化分配。两个 layer 分别读取各自的七份矩阵权重，固定合成 recipe 的 weight salt 为 0 和 17；独立 KV 区域保留。全程一套原 Matrix、一套 pinned iDMA，无旧 BlockLaunch、无 Host 中间态写入、无层间 reset。

## 完整数值结果

42/42 completion，18 Matrix / 22 SFU / 2 KV 命令；检查 40 份实际输出 tensor，共 1,409,024 个 FP32 值，全部 bit-exact。全部 actual/reference 文件及逐元素 CSV 已保存，不以最后一个 hash 代替完整比较。

- Wall cycles：146,854,495。
- Useful MAC：1,498,202,112；实际执行 MAC：1,524,105,216。
- DDR 读取：385,152,512 bytes；成功写回 ACK：5,636,096 bytes。
- 原 iDMA transfers：6,106,072；metadata reads：472。
- 最终 Y1 FNV64：`8401b1b4297c40b0`。

这些是固定数值合同、合成权重的双层仿真计数，不是官方模型吞吐，也不是 800 MHz 物理签核。

## 沙箱独立验证

重新读取 CI 全部数据及 ABI，1,409,024 行 CSV/二进制检查通过；253 个被测源文件核对通过。两份证据目录的 Git tree 与本地原始工件一致：numerical 111 文件，frontend 18 文件。完整 CI 发布目录共有 134 文件。

独立 NumPy 路径另完成三项检查：第一层全部 704,512 个实际值与旧 real16 实际输出一致；直接从实际 Y0 重算第二层 InputNorm 的 24,576 个值一致；直接从第二层实际前驱 tensor 重算七个 GEMM 的 368,640 个值一致。后两项不读取参考 tensor 作为输入。

本地实际 Chisel 前端控制测试 9/9；两个独立核验器的 12+7 项单测在普通及优化 Python 下通过；对真实 CI 工件副本做七种破坏均被拒绝。另在生成的真实尺寸 Matrix/iDMA DUT 上完成七项早期错误拒绝，包括已写 98,240 bytes 后的最后写响应错误。该负向门禁验证 lockout，不宣称本次又完成所有故障后的 reset recovery。

沙箱重复长仿真在 CI 完整结果核验后停止，已完成的 18 份 actual tensor / 655,360 个值与 CI 一致；它不是第二份完整双层 PASS。编译失败尝试、部分运行和全部文件均保留，没有修改生成 RTL。

## 执行 agent：不修改代码

只读复核已有完整证据，仅需 Python、NumPy、PyYAML，在最新 main 使用一个全新输出目录：

```bash
OUT="$PWD/work/rechecks/real2_$(date -u +%Y%m%dT%H%M%SZ)"
bash chisel/continuous_prefill/scripts/recheck_real_two_layer_delivery.sh "$OUT"
```

必须得到 `gate.exit=0` 和 `PASS_REAL16_TWO_LAYER_DELIVERY_RECHECK`。该命令只读 Git 内的既有数据，不重新仿真。

重新执行完整双层仿真，使用原已锁定的 Java/sbt/Verilator/HardFloat 和 iDMA 环境：

```bash
export IDMA_EXPORT=/absolute/path/to/verified/idma_export
OUT="$PWD/work/results/real2_$(date -u +%Y%m%dT%H%M%SZ)"
bash chisel/continuous_prefill/scripts/run_real_two_layer_gate.sh "$OUT"
```

必须有零退出码、42 completion、430 descriptors、38 owner jobs、1,409,024 个零差异值，以及 `REAL2_ACCEPTANCE.json` 中的 `PASS_REAL16_TWO_LAYER_HOST_NUMERICAL`。失败只保留目录和原始日志并反馈；不改 Chisel、RTL、配方、阈值或 receipt。缺工具为 BLOCKED，不计 PASS。

## 后续范围

当前真实尺寸双层 real16 已闭合。下一关仍使用原 Host 生产链验证真实尺寸 32/33-token，再扩展 token 数和层数。当前 maxCommands=64，不等于能接收完整 28 层 588 条命令；扩展前需要开发侧完成命令容量及 tensor 生命周期方案。官方权重/独立模型质量、q1024 整网和 1.250 ns DC 分开验收，不把本次双层合成数值结果升级为整网推理完成。
