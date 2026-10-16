# U00.2：完整 M16 packed Public 的 assigned 官方门限通过（2026-10-16）

## 实际执行结果

- 全新目录的真实完整原始 Public21 执行，外层与子进程实际退出码均为 0，清理完成；总耗时 591.280260 秒。原始数值段耗时 569.456837 秒，前缀 32.708202 秒。
- 21 个 Public 完成、17 个 owner jobs、19 个封存输出；28 个观测阶段中的 27 个 assigned 官方门限全部通过，softmax_fp32 保持未分配门限的诊断阶段。15 个 whole outputs 与6个 observed nodes的固定算术比较逐位通过。
- 10 个 Attention 捕获字段全部完整，因果掩码范围和 packed multiplicity 规则保持。EVIDENCE 记录各阶段 max/mean 误差和实际/参考 SHA256，不含张量或权重。
- 修复仅将严格 profile 的 Job 类型绑定到真实 Host 发出的 PrefixJob；首次失败及其原始启动器源码保留。没有继承首次失败或小样本 PASS。

## 固定身份与预算

执行 contract：`f5e3c0ecc342019923dc8759168e9097c9d0e1ffc1d7eac0a56032569fa33882`。
修复 pins：`a75d74af5d36774b60f608b24bb62541ff397f701ea509339a9b3b74b3508542`。
运行时 316 个源文件，源映射 compact SHA256：`c27020ddcc0965e18026063640e54d2daa2e00ec7f17fbbb82730bd9c233bfdf`。
快照使用 pretty JSON 的源映射 SHA256：`0153488576891aa9d54e0f2aef231a3f08a8ad1c10d96765a52e4052d8453a8e`；两种编码不混用。

原始数值900秒，工作924秒、清理5秒、总上限930秒，均未提高。使用真实 be00 Git 来源、同PID重执行、已验证的13个官方张量、新生成M16双参考和严格合并ELF；本次没有下载、构建或重跑官方 native forward。

## 验收边界与下一步

- [x] 原始完整 M16 软件链真实执行和27个 assigned 官方观测门限。
- [x] 原始安全 summary/progress/SUPERVISOR 字节保存；调用方记录真实工具退出码。私有完整报告、路径、日志、二进制及载荷不公开。
- [ ] 完整29节点：explicit_mask_tensor尚未单独观察；scores/logits/prob/softmax_fp32仅因果区域，future scores未物化。softmax_fp32无assigned数值门限。
- [ ] 固定三模型 batch=1、M=128典型block、实际RTL、useful wall MAC≥90%。本证据的相关全局验收标志均为false。
- [ ] 先依据本次真实阶段/计数证据评估M128原始预算与软件模型开销，再决定保持算术/资源语义的优化；不把M16耗时的线性外推视为实测，不仅提高超时。

本阶段状态严格为 PASS_ASSIGNED_OFFICIAL_OBSERVED_GATES_ONLY。独立冷测试与执行结果的复核分别保存，不从安全结构校验器单独推断真实执行。
