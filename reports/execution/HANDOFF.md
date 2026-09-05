# 交接：三模型 q1024 性能闭环

- 本文件硬限制：不超过40行；历史证据留在阶段报告。
- Goal BLOCKED_DECISION；main；待批准OProj/Down/residual精度，未完成三模型整网验收。
- 计划：reports/THREE_MODEL_Q1024_PERFORMANCE_PLAN.md。

## 当前状态

- Qwen2 首层 K/V 投影：各1024行、262144个BF16输出逐位通过。
- 各4272278周期；名义800MHz下5.340ms，MAC利用率18.41%。
- 证据：reports/execution/Q1024_CONTINUOUS_{K,V}_RESULT.json。
- Q完整1024行、1572864个BF16输出逐位通过，25656608周期、利用率18.39%。
- Q自动执行器已结束；17段连续状态/hash经收集器验证，不需重跑。
- attention前512 query独立FP32检查786432项通过，max error0.000146538；非整网PASS。
- 撤回旧attention shortreal容差PASS；必须以独立FP32输出校验为准，非整网PASS。

## 唯一下一动作

等待用户明确精度选择；已有q1024持久任务未停止/重启，不轮询其进度。

- 真实1024行bias/RoPE共3932160个BF16值通过；实际输出已接attention输入。
- receipts/实际FP32：work/results/q1024_captured_attention_payload/；64分区自动运行。

## 执行约束

- CPU8-23；一次一个重任务；Verilator j4/DC8。
- MemoryHigh24G/Max30G；可用内存>10GiB、磁盘>50GiB。
- 每条重命令≤600秒；systemd --wait/子进程wait阻塞等待，不循环查状态。
- 禁止重编模拟器、改夹具或已保存的Tcl脚本；禁止手改生成RTL。
- 持久服务依次执行剩余attention→独立校验/组装→CPU参考→OProj夹具；非整网PASS。
- QT42原父进程消失，子进程结束后独立24576项核验通过；退出码未知，未重跑。
- IEEE754替代helper两模拟器通过，待全量结束再接入；运行中不改冻结源/夹具。
- 保护两个被排除的用户runtime脚本；检查点及时commit/push。

## 未完成

- OProj/Down/residual的BF16-vs-FP32合同待用户选择；28层链、Qwen3.5/3.8及PPA未闭环。
- golden按token复用仅适用于首层norm/raw QKV，禁用于RoPE/attention/后续层。
- DDR100/40GBps仅带宽上限模型；尚缺完整模型性能证据。
- 已向用户询问Qwen3.8权重/参考路径，尚无答复。
