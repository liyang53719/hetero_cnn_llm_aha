# 交接：三模型 q1024 性能闭环

- 本文件硬限制：不超过40行；历史证据留在阶段报告。
- 精度策略已批准，实施中；main；矩阵BF16/累加FP32，必要边界FP32；三模型未验收。
- 计划：reports/THREE_MODEL_Q1024_PERFORMANCE_PLAN.md。

## 当前状态

- Qwen2 首层 K/V 投影：各1024行、262144个BF16输出逐位通过。
- 各4272278周期；名义800MHz下5.340ms，MAC利用率18.41%。
- 证据：reports/execution/Q1024_CONTINUOUS_{K,V}_RESULT.json。
- Q完整1024行、1572864个BF16输出逐位通过，25656608周期、利用率18.39%。
- Q自动执行器已结束；17段连续状态/hash经收集器验证，不需重跑。
- q1024 attention全部1572864个FP32独立核验通过，max error0.000146687；非整网性能PASS。
- 撤回旧attention shortreal容差PASS；必须以独立FP32输出校验为准，非整网PASS。

## 唯一下一动作

OProj→residual已排队（session66976/77257）；阻塞等待，不轮询、不重复启动。

- 真实1024行bias/RoPE共3932160个BF16值通过；实际输出已接attention输入。
- OProj receipts/实际FP32：work/results/q1024_captured_oproj_replay/；构建通过，数值未关闭。

## 执行约束

- CPU8-23；一次一个重任务；Verilator j4/DC8。
- MemoryHigh24G/Max30G；可用内存>10GiB、磁盘>50GiB。
- 每条重命令≤600秒；systemd --wait/子进程wait阻塞等待，不循环查状态。
- 禁止重编模拟器、改夹具或已保存的Tcl脚本；禁止手改生成RTL。
- residual流协议100包通过；真实加法回归等待OProj实际输出，非数值/整网PASS。
- QT42原父进程消失，子进程结束后独立24576项核验通过；退出码未知，未重跑。
- IEEE754替代helper两模拟器通过，待全量结束再接入；运行中不改冻结源/夹具。
- 保护两个被排除的用户runtime脚本；检查点及时commit/push。

## 未完成

- 策略3/写回10/解码16/DMA布局4用例通过；真实FP32 OProj、residual及整网/PPA仍待验证。
- golden按token复用仅适用于首层norm/raw QKV，禁用于RoPE/attention/后续层。
- DDR100/40GBps仅带宽上限模型；尚缺完整模型性能证据。
- 已向用户询问Qwen3.8权重/参考路径，尚无答复。
