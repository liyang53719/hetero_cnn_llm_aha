# 完整 block 监督器的失联观测补充

launch.py 复用已发布 qwen2_live_fullblock_model_m128/launch.py 的准入、预算、RSS、输出和日志检查，以及进程组清理。没有改变计算或参考代码；当前原准入仍会拒绝缺失的 bootstrap 等证据，不能用此模块直接宣称业务恢复。

新增独立 .HEARTBEAT.json：启动、每 10 秒、终态保存 UTC、elapsed、worker/supervisor PID、已采样 RSS/磁盘量、可观察 returncode、PROGRESS.jsonl 最后一条阶段。阶段读取最多尾部 64KiB，截断/缺失明确报告，不解析张量。heartbeat acceptance 始终 false。

写入使用临时文件 flush/fsync、原子 replace、目录 fsync；launcher/heartbeat 各 1MiB 上限，普通结果元数据 32MiB 上限。额外 heartbeat 位于 worker 目录外，为固定大小独立开销。TERM/HUP/INT 可捕获时进入原进程组清理；SIGKILL/环境销毁仍无法保证终态，历史 STARTED 不代表当前仍运行。没有自动重试或状态续算。

测试：python -B -m unittest candidates.qwen2_supervisor_recovery.test_observation -v

9 个方法通过，0.289 秒：正常/非零短假 worker、子进程向监督器发送 TERM 后清理/reap、信号处理器恢复、截断/缺失阶段、原准入阻止 spawn、replace 故障注入保留旧记录、post-spawn 写盘异常清理 worker、重复信号不打断清理、Popen 返回赋值前信号窗口不遗留 worker。信号 handler 只锁存，在获得 child 后的安全点处理。全部是监督协议测试，无权重、业务数值或 RTL。业务阶段生产端与真实长链尚未运行。

实际接入阻塞：原 reviewed-source-manifest 尚不覆盖此新 sibling 的 launch/observation。正式 --actual 前必须将新监督器和恢复适配代码纳入独立审查的完整闭包；旧 manifest 不证明新 wrapper 已获审查。持续写盘故障时最终 receipt 也可能无法持久化，但 post-spawn 异常仍尝试有界进程组清理。
