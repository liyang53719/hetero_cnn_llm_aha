# U00.2：首次完整 M128 尝试的准入失败归档（2026-10-17）

## 真实终态

- 单次完整 M128 启动尝试已执行；实际工具会话 55239、终态块 503263，调用方记录外层退出码 1，子进程退出码 1，31.690888 秒结束且清理完成。
- 同 PID 6 在 31.028968 秒进入 numeric 阶段，随后确实调用数值入口。因此 numerical_run_started=true；这不表示 Public 主循环或完整链已经执行。
- 固定的 M128 模式检查和运行授权通过后，dense_block_reduce/check_public_numeric.py:306 仍保留 rows==16 的 raw KV 条件，拒绝真实 rows=128。异常为：ValueError: enabled raw KV execution is limited to M16 pending a reviewed same-source M16 receipt。
- 该异常发生在 verify_snapshot（308）、runtime（309）、输出目录创建（313）及实际报告初始化（314）之前。没有 actual 输出目录、实际 summary 或 CHILD_COMPLETE；Public 主循环、owner job、数值比较均未进入。这是集成准入拒绝，没有观测到数值不一致，也不是超时。

## 原始身份与可复核范围

执行 wrapper contract：582833958e1dda4772f3e23c02f2ec0a17be9d6d7e5e3e5fba36618fb4ca8f30。

入口 pins：ce0b54f6c73eec52736feb22e89b72ef388427b8abce04865a135dff76790a42。

346 源 compact-map SHA256：f5e1dcdecc406750cd6409e45a97184294ba94d4e61cb9ef67d53641fd912104。归档时只读核对全部 346 个 installed 文件和全部 346 个 overlay 文件，均与原始 SOURCE_PROOF 一致；真实 Git HEAD 为 be00eb8e4bc75e2e41f2a434d05d4c901ed3faa5，已提交标量源码字节未变。

SOURCE_PROOF SHA256：0c219515d4ebe6032747c0d120645d8467ab1172d8ddd235e06818f103bd0a55。

安全 summary SHA256：9c3bf942839a5563b3cba2df86bf2ec5c020fe3e99b123f25c8c38bc7f10d1fc。

summary、progress、SUPERVISOR 是原始安全 JSON 的逐字节副本。EVIDENCE 用字节数和 SHA256 绑定原始调用、来源、输入、快照及失败日志；仅记录安全异常文字、仓库相对源码帧和必要状态。完整 stderr（1517 字节）及私有文件、路径、权重、数组均不公开。外层退出码来自实际调用方终态，不由子进程结果推断。

## 边界与下一步

- [x] 保留真实失败；没有改写已执行源码、旧证据或私有原件，没有再次运行数值、producer 或编译。
- [x] 新归档冷测试拒绝 PASS 继承、未执行误标、完成链误标、非有限数值、重复或未知字段以及篡改的原始副本。
- [x] 原有 M17 observer 小样本 PASS 不得转移到本次完整 M128；所有 numerical、assigned gates、full29、RTL、hardware、90% 验收标志均为 false。
- [ ] 单独准备严格的新源码后继，仅修复已证明的准入冲突；保留旧源、原始 27 个 assigned 官方门限及比较路径。
- [ ] 新源码冻结、独立复核和运行门禁完成后，才能在新目录另行尝试；不得覆盖本次失败。

本归档只固定首次失败的证据，不构成 M128 数值通过、完整 29 节点通过、RTL 执行或 useful wall MAC ≥90% 证明。
