# U00.2：首次完整 M16 packed Public 尝试保留失败（2026-10-16）

## 实际结果

- 独立审查和授权后的单次尝试，外层/子进程实际退出码均为 1。50.526777 秒终止，清理完成，远低于 900 秒数值 / 924 秒工作 / 930 秒总上限。
- 真实原始 Public 前缀完成 PC0–9，共 10 个请求、10 个完成和10次发布，耗时 32.397361 秒。未出现完整 launch terminal。
- PackedM16PublicProfile.install 在进入 Attention 前拒绝，错误为“exact idle original M16 Public packed profile required”。失败捕获中 Attention job 与 terminal 均为空；尚未进入数值比较。这是集成准入失败，不是已观测数值不一致。
- 本次固定 be00 genuine Git、313 个安装源、同 PID/同期限重执行、已准备的新 M16 双参考和严格合并 ELF；没有下载、编译或改写旧来源。

## 固定身份

执行 wrapper contract：`6211582598199f558d3fcbd1be79eed653e98b37f7bb804b93449262bfec0d22`。
入口 pins：`10b301c3897430c7aebd2cd1ee245d5143e1886432a5544bf8f3656d3c85c5d5`。
运行源映射：`c8e34f38cccd395e802a1674300b6accc382368b28d771232b25eeabdd23acd3`。

summary/progress/SUPERVISOR 保留原始安全 JSON 字节；EVIDENCE 仅记录各私有/安全文件身份、固定错误类别、计数、耗时和范围。私有完整实际报告、失败捕获、数组、日志、二进制和运行位置不公开。日志仅保留 SHA256/字节数。调用方 SUPERVISOR 记录真实工具终态，不从子进程报告推断外层成功。

## 检查表

- [x] 真实完整程序尝试，保留成功的前缀进展和失败现场。
- [x] 所有27个 assigned 官方门限、10字段观测和原始比较函数未被放宽；入口/启动器44+44冷测试后运行。
- [x] 失败不冒充超时、数值 PASS、完整链完成或未执行；numeric_started=true，Attention_started=false。
- [ ] 用原始 Host 发出的实际 Job 类型验证严格 profile 准入，冻结新修复后独立审查。
- [ ] 获得新的单次重试授权后，在全新目录使用相同预算运行；不得覆盖或继承本次结果。
- [ ] 完整 M16 的27个 assigned gates，再继续固定三模型 batch=1/M=128典型 block、实际 RTL、useful wall MAC ≥90%最终目标。

numerical/full29/RTL/hardware/90%标志均为 false。失败文件的存在或已有小样本 PASS 不构成完整验收。
