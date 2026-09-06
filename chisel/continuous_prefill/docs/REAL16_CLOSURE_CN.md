# Qwen2-1.5B real16：完整连续单 block 已验证

被测源码提交：`b91bbe3eed98ccf47362fc9a5a6c3d26d002d552`。本记录来自当前沙箱实际编译、生成、仿真，不是引用旧 CI 的通过标签。

## 验收范围

真实几何：hidden=1536、FFN=8960、12 Q heads、2 KV heads、head_dim=128；实际执行16 tokens、1个完整decoder block。max_tokens=1024只是编译容量，不是本次请求长度。

使用确定性合成权重（seed=20260906）和固定BF16/FP32有序数值合同。主计算路径是16个BF16 FMA lane的功能实现；不声明官方checkpoint、原512-MAC、Command128/pinned-iDMA、整网、多层、q1024或800MHz时序签核通过。

## 实际结果

- 仿真正常退出0；15个阶段在一次launch、同一DDR内存模型中连续执行。
- 全部663,552个FP32输出逐字比较，bit differences=0；最终输出24,576个值。
- 实际成功写回ACK累计2,654,208 bytes；useful/executed MAC均为749,101,056。
- DUT总周期：83,418,738。这是功能路径计数，不能作为原512-MAC NPU的性能。
- 相关Chisel DUT单测38/38、证据校验Python单测23/23（另15个subtest）、同一真实尺寸DUT的4个错误/非法启动用例通过。
- 保存全部31份输入/actual/reference二进制文件和663,552行逐元素CSV；独立重读二进制与CSV再次检查一致。
- 真实输出工件的单bit修改、最终tensor缺失、Down短文件、actual/reference同时为NaN，4类均被拒绝。

| phase | 阶段 | 检查FP32值 | bit differences | 累计阶段周期 |
|---:|---|---:|---:|---:|
| 0 | InputNorm | 24,576 | 0 | 158,048 |
| 1 | Q projection + bias | 24,576 | 0 | 3,831,090 |
| 2 | K projection + bias | 4,096 | 0 | 4,452,693 |
| 3 | V projection + bias | 4,096 | 0 | 5,074,406 |
| 4 | Q RoPE | 24,576 | 0 | 5,100,868 |
| 5 | K RoPE | 4,096 | 0 | 5,105,248 |
| 6 | causal GQA Attention | 24,576 | 0 | 5,565,700 |
| 7 | OProj | 24,576 | 0 | 9,235,893 |
| 8 | Residual | 24,576 | 0 | 9,268,448 |
| 9 | PostNorm | 24,576 | 0 | 9,426,603 |
| 10 | Gate projection | 143,360 | 0 | 30,780,168 |
| 11 | Up projection | 143,360 | 0 | 52,132,669 |
| 12 | SiLU(gate) * Up | 143,360 | 0 | 62,018,140 |
| 13 | Down projection | 24,576 | 0 | 83,386,025 |
| 14 | Final residual | 24,576 | 0 | 83,418,744 |

## 连续性的检查

DDR服务只处理读写，不计算模型算子。中间区域初始化为NaN毒值；DUT写入只有在成功response握手后才对读请求可见。消费者读取未写入或未发布的区域立即失败；禁止重复写、写入其他阶段、Host在运行期初始化中间数据。对未使用的1024-token保留区域检查毒值未改变。参考结果仅比较和导出，不用于服务DUT读取。

Chisel `BlockWritebackFence`按实际成功ACK的byte-enable计数，未收到完整阶段写回不得发布。Dense按16-token块复用权重，FP32累加按原来递增K顺序进行，不采用改变归约顺序的split-K。Dense行缓存573,440 bytes；另有有界elementwise与score/probability暂存。`evidence/DDR_REGIONS.csv`记录本次准确DDR区域及活动字节数。

## 本地只复核与执行

```bash
git switch main
git pull --ff-only
OUT="$PWD/work/results/qwen2_real16_$(date -u +%Y%m%dT%H%M%SZ)"
bash chisel/continuous_prefill/scripts/run_qwen2_real16_gate.sh "$OUT"
```

要求Java、sbt、Verilator、g++、Python3和锁定的HardFloat依赖；缺工具返回77/BLOCKED，不算PASS。输出目录必须是新目录。不得改Chisel、生成SV、参考模型或容差；任何失败仅返回命令、commit及首次错误日志，由开发侧修复。

复核`RESULT.json`状态、15个STAGE_CHECK/STAGE_MEMORY、simulation.exit=0及逐元素CSV。不同工具/目录生成的调试注释会影响SV文件哈希；哈希用于绑定每一次执行，不要求不同目录的生成文件逐字相同。数值门槛不因此放宽。

## 工件与来源

Git中的本轮原始日志和收据位于`reports/execution/QWEN2_REAL16_B91BBE3/`。完整交付ZIP含被测源代码、生成DUT、编译/测试日志、全部tensor和逐元素CSV。没有把未完成的生产集成或物理签核任务计入本关。
