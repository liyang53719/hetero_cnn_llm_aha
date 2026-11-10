# 35B L0/L3 有界真实权重获取

仅下载固定revision的L0/L3全部张量，保留所有256专家，不下载整checkpoint。原官方header范围经过verify_bundle；先8字节严格206探测成功，再两worker、每请求最大8MiB、单请求90秒、总7200秒、零自动重试获取。

输出目录独占创建，partial不当成功，逐tensor完成后rename并记录观察SHA/所有HTTP receipt，全部完成才写终态。现有观察SHA并非独立预先pin，不声称checkpoint LFS SHA已验；不声称模型/Chisel/RTL执行或利用率。

数据只在本地，不提交bin/partial或文本编码数据。源码/身份/进度摘要允许传递。发生失败保留partial和归因；不要在原任务状态不明时重复启动。

## 本轮失败与明确限制
原session54985已终态FAIL_OR_INCOMPLETE，110.16秒，Python报RemoteDisconnected；执行工具进一步明确us.aws.cdn.hf.co:443被网络策略阻断。L0/L3各67,108,864字节partial，完整tensor均0。初始8字节206探测成功不代表后续CDN始终可用。无绕过、无重试。

更正receipt保存范围：v1仅每tensor完成后保存全部receipt，因首tensor未完成，现有文件仅保留每层最新range receipt；不声称前七段HTTP receipt已持久化。全部partial已本地SHA重验保留，此SHA仅本地完整性而非独立provider认证。

新增v2候选修复逐range写入并fsync JSONL journal、worker失败立即通知peer停止，避免失败丢receipt/继续无益下载。v2仅Python语法检查，尚未下载或执行，不替换本次已记录执行源码，不绕过网络策略。
