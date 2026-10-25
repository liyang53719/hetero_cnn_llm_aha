# Qwen2 M2 三轮旋转顺序观测成本诊断（未采用）

详见 [`candidates/qwen2_attention_stability_diagnostic`](../candidates/qwen2_attention_stability_diagnostic/README.md)。三次 fresh 进程各执行 off / original / selective_identity_r1，三轮依次轮换物理顺序；保留实际顺序与全部汇总，不改写原始 traces。独立实际审核 64,530 checks、347 artifacts、1,026 pins，通过范围仅为已保存的 M2 数值／控制／字段／参考／监督收据闭环。

三对 candidate/original CPU 比为 0.6296326146496655、0.5758723841200312、0.5370334317265438；只说明这三对 owner 区间样本，**不是统计证明、稳定加速或采用结论**。比较包含 selective-LINE 与 identity cache 两项变化，不是 cache 单项收益。三个循环旋转不等于全部六排列、随机化或完整 carryover 平衡；此前 R4 与单组三臂是另一次运行，不能作为本次受控分母。

总计 CPU 18.79356525 s / wall 19.15878644003533 s。内存策略是逐进程 1 GiB RLIMIT_AS 加采样 combined RSS，不是聚合硬上限/cgroup。最终 RSS 16,633,856 bytes 和另六个保存样本都只是 supervisor-only 点采样，**没有 live combined RSS 历史或峰值，不能声称独立验证峰值 ≤ 1 GiB**。无单独 live affinity/RLIMIT 快照或完整 OS 调度／wait／reap 事件历史；相关限制完整保留。

仅新增六份原字节源码、两个原样复制的非执行式包装工具、可重建 22 文件的相对路径清单、逻辑 pins 及脱敏证据。包装没有重跑 target/native/原始 mocks。保留 reference normalizer 8/16 次与 DUT 1 次频次差异；只对数值、presence、shape 等实际一致性作结论。历史 fixture slowdown、R1 BLOCKED、full M128 CPU-limit FAIL / INCOMPLETE、RTL 0/5 和尚未达成的利用率目标均不升级。没有采用、没有新增硬件验收。
