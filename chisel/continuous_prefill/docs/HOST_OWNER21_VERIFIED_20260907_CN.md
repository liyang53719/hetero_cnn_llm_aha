# Qwen2 real16：Host 原算子命令驱动全部 block owner 已验证

## 冻结身份与真实完成范围

被测源码：`6d39c76aa1420cb42564c530860f6c32cd8cc41d`。
实际硬件运行：GitHub Actions `34082332510`。
完整证据发布提交：`b8253133b3f2964775fe43e72d099c1edc567f05`。
永久证据目录：`reports/execution/HOST_OWNER_21_6D39C76_CI/`。
独立沙箱复核：`reports/execution/HOST_OWNER_21_INDEPENDENT_20260907/RESULT.json`。

这次不是先自动运行 block，再接三条演示 Add。HostBlockTop 不暴露旧 BlockLaunch 或外部 phase 许可。命令、typed descriptor 和 payload 经同一共享仲裁器与一套原 pinned iDMA；原 Matrix endpoint 只有一套。每个作业由 DDR 读回的命令、policy、shape 与地址驱动，消费者读取前驱实际写回的数据。

硬件源码为 Chisel。此轮恢复验证不需要改写既有算术 Chisel，也没有修改任何保留 RTL 或生成 SV；修复的是 CI 缺少 NumPy/PyYAML，以及证据发布时将生成文件末尾空行误判为失败。生成文件保持原始字节和哈希，未通过编辑 SV 消除告警。

## 已验证结果

真实配置：16 tokens、hidden=1536、FFN=8960、12 Q heads、2 KV heads、head_dim=128。MAX_TOKENS=1024 是编译容量，不是本次实际 token 数。

| 项目 | 结果 |
|---|---:|
| Host Command128 完成 | 21/21 |
| Matrix / SFU / KV 命令 | 9 / 11 / 1 |
| 实际 owner 作业 | 19 |
| 逐字检查 FP32 输出 | 704,512 |
| Bit differences | 0 |
| Useful / executed MAC | 749,101,056 / 762,052,608 |
| 完整请求仿真周期 | 73,425,016 |
| DDR read / 成功 write ACK bytes | 192,576,256 / 2,818,048 |
| iDMA transfers | 3,053,036 |
| Metadata read beats | 236 |
| Host 中间写入 / 旧 BlockLaunch | 0 / 0 |
| 最终输出 FNV64 | fe9744aaa5c1c9ad |

QK、Softmax、PV 三条原始命令使用已校验的流式融合合同，所以 21 条命令对应 19 次 owner 作业。三个 completion 保守地延迟到 PV 最终写回后发布。逻辑 score/probability descriptor 不表示已物化 DDR tensor；这些区域未被访问，不能供普通后续命令读取。

新增 raw Q/K/V 与 KV 两个 cache view 的检查，使输出数从旧 15 阶段的 663,552 增为 704,512。旧版对应的 15 份实际输出与本次实际输出逐字相同，不只是新 oracle 自洽。KV_APPEND 验证实际 K/V 到冷启动连续 cache 的写入，不是分页 KV 或增量 decode。

Tiny16 同样通过：H64/F128，21 命令、19 作业、19,968 个输出零差异。完整 real16 硬件结果来自实际 CI 仿真；沙箱独立重读两份 CSV 共 724,480 行及二进制，重查公共 ABI 和 228 项源码清单。证据变异套件 15 个用例在普通 Python 和 -O 下均通过，两个模式不重复计数。未在这些证据中执行的新增故障/重复请求脚本不自动算作通过。

两个发布子目录分别含 63 个文件。沙箱从原 CI 字节重算 Git tree，tiny16 为 `07a4fd37120af92b2a07b420883b005cf976e75b`，real16 为 `0d1d3b4883cf0e18aa279354bafc119de0fa19dd`，均与远端一致。完整输出、CSV、生成电路和日志不是只保存在短期 artifact。

## 执行 agent：只复核或运行，不修改代码

优先复核固定证据，无需 Java、Verilator、DC 或模型权重：

```bash
EVIDENCE=reports/execution/HOST_OWNER_21_6D39C76_CI
python3 chisel/continuous_prefill/scripts/verify_host_block_gate.py "$EVIDENCE/tiny16" --read-only
python3 chisel/continuous_prefill/scripts/verify_host_block_gate.py "$EVIDENCE/real16" --read-only
```

Python 依赖需包含 NumPy/PyYAML；验证环境使用 NumPy 2.3.5、PyYAML 6.0.3。禁止修改阈值、预期数量或输入文件来绕过失败。

具备 Java17、sbt、Verilator、g++ 和锁定 iDMA export 时，在全新输出目录复跑：

```bash
export IDMA_EXPORT=/absolute/path/to/verified/idma_export
bash chisel/continuous_prefill/scripts/run_host_block_gate.sh tiny /absolute/new/owner_tiny16 16
bash chisel/continuous_prefill/scripts/run_host_block_gate.sh real /absolute/new/owner_real16 16
```

成功必须同时满足 gate.exit=0、simulation.exit=0、RESULT.status=PASS_HOST_DRIVEN_QWEN2_OWNER_BLOCK，以及本页对应的完整数值/命令计数。缺少依赖是 BLOCKED，不是通过。失败仅保留目录并反馈 commit、命令、首次错误和原始日志，由开发侧修复。

## 保持开放的门槛

当前为确定性合成权重、FP32 容器/BF16 入口、固定有序 FP32 累加配方。没有声明原 GGUF descriptor 二进制镜像兼容、官方框架误差/模型质量通过、多层、整网 q1024 或 800MHz DC 通过。

下一开发顺序：在相同 Host-owner top 上完善跨 token tile、地址重定位、第二请求及真实 iDMA 故障回归；随后接入不同权重的多层原命令图和实际权重转换/独立参考；再扩大到 q1024。当前保持 Qwen2 共同基础主线，不以新增模型清单替代这些验收。设计修改仍在 Chisel，执行 agent 不承担编码任务。
