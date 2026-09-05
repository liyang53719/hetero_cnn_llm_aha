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
- 单投影结果不等于完整decoder或模型prefill。

## 唯一下一动作

等待真实Matrix数值测试(session14037)，通过后接attention内存/SFU。

- 数值测试已获得锁并开始编译；进度见ATTENTION_ENDPOINT_PROGRESS.json。
- 收集器：scripts/collect_q1024_projection_chain.py。

## 执行约束

- CPU8-23；一次一个重任务；Verilator j4/DC8。
- MemoryHigh24G/Max30G；可用内存>10GiB、磁盘>50GiB。
- 每条重命令≤600秒，阻塞等待；Q恢复段为2ms模拟时间。
- 禁止重编模拟器、改夹具或已保存的Tcl脚本；禁止手改生成RTL。
- 中断后先查receipt/PID；仅显式 --retry-failed 可重试失败段。
- 保留完整 .chk/.chk.FILES/.chk.ucli；快照不提交Git。
- 恢复控制使用已验证的UI变量基线修复；不手改快照数据。
- 保护两个被排除的用户runtime脚本；检查点及时commit/push。

## 未完成

- decoder其余部分、28层链、Qwen3.5/3.8、当前DC/PPA。
- golden按token复用仅适用于首层norm/raw QKV，禁用于RoPE/attention/后续层。
- DDR100/40GBps仅带宽上限模型；尚缺完整模型性能证据。
- 已向用户询问Qwen3.8权重/参考路径，尚无答复。
