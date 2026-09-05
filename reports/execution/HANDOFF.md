# 交接：三模型 q1024 性能闭环

- 本文件硬限制：不超过40行；历史证据留在阶段报告。
- Goal ACTIVE；main 分支；完整模型 q1024 性能仍为0/3。
- 计划：reports/THREE_MODEL_Q1024_PERFORMANCE_PLAN.md。

## 当前状态

- Qwen2 首层 K/V 投影：各1024行、262144个BF16输出逐位通过。
- 各4272278周期；名义800MHz下5.340ms，MAC利用率18.41%。
- 证据：reports/execution/Q1024_CONTINUOUS_{K,V}_RESULT.json。
- Q完整1024行、1572864个BF16输出逐位通过，25656608周期、利用率18.39%。
- Q自动执行器已结束；17段连续状态/hash经收集器验证，不需重跑。
- Q证据：reports/execution/Q1024_CONTINUOUS_Q_RESULT.json。
- 撤回旧attention shortreal容差PASS；必须以独立FP32输出校验为准，非整网PASS。

## 唯一下一动作

等待q1024 attention(PID1884540/session68910)；独立FP32校验/组装器session75376。

- 真实1024行bias/RoPE共3932160个BF16值通过；实际输出已接attention输入。
- receipts/实际FP32：work/results/q1024_captured_attention_payload/；64分区自动运行。

## 执行约束

- CPU8-23；一次一个重任务；Verilator j4/DC8。
- MemoryHigh24G/Max30G；可用内存>10GiB、磁盘>50GiB。
- 每条重命令≤600秒，阻塞等待；Q恢复段为2ms模拟时间。
- 禁止重编模拟器、改夹具或已保存的Tcl脚本；禁止手改生成RTL。
- 旧hash-only回放在QT7结束后停止并保留；新回放导出实际tensor供OProj。
- 保留完整 .chk/.chk.FILES/.chk.ucli；快照不提交Git。
- 检查首个失败，不放宽0.002；运行中禁止改attention源/夹具/二进制。
- 保护两个被排除的用户runtime脚本；检查点及时commit/push。

## 未完成

- decoder其余部分、28层链、Qwen3.5/3.8、当前DC/PPA。
- golden按token复用仅适用于首层norm/raw QKV，禁用于RoPE/attention/后续层。
- DDR100/40GBps仅带宽上限模型；尚缺完整模型性能证据。
- 已向用户询问Qwen3.8权重/参考路径，尚无答复。
