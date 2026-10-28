# 官方固定 revision 权重恢复续传 — 原始字节完成，数值 INCOMPLETE

用户新增网络授权后，原运行身份先诊断，原始已验字节复用；未修改代理/安全设置，不走替代来源。T2253 因环境重连失去进程，保留 52 张量；T2258 在 HTTP206/正确范围但短响应体时严格停止，保留 66 张量及成功的连续前缀。原短响应未写盘且未记实际短长度，不能补造。

对 51+47 个前缀分块逐一核原 URL、固定语义计划、连续范围、长度、SHA、header SHA/ETag，再复制到新目录；不使用失败块。恢复 822,083,584 字节前缀与 66 个完整张量后，T2315 原进程 exit0，70/70 原始张量共 3,531,306,272 字节完成。全部 70 再次独立哈希并核固定官方计划字段；P0/P1/P2/P3/P4 分别12/14/11/18/15张量。35B 完整专家权重，不是选定专家子集。

35B 历史 digest 集合仅作独立一致性核验，语义身份来自官方固定 revision/header tensor name/range。Qwen2 仅 fresh 原始 payload hash，不能称旧 transformed source hash 命中。仅 raw source bindings 完成，不是逻辑 provider、独立参考、Chisel 或 RTL 数值通过；五块完整 Chisel/RTL 仍 0/5。

## 源码与复现
本目录 `acquire_resumable.py` 依赖同级 `../five_profile_input_recovery_20261028` 已发布固定 plans/headers/pins/reconstruct_plan.py。仅将实际脚本的依赖目录解析从工作目录改为仓库相对路径，未冒充 portable 版本网络重跑。实际执行 source SHA 在 ACTUAL_COMPLETE.json；当前文件 SHA 在 MANIFEST.json。

人工确认合法网络访问后显式执行 `python acquire_resumable.py --output NEW_LOCAL_DIRECTORY --reuse-from VERIFIED_PRIOR_DIRECTORY --execute`。只允许原固定 HTTPS source，最多2请求、8MiB分块、完整总量上限，所有终态失败即停止，无自动重试；新目录、旧日志/partial 不覆盖。headers重新验证后才能复用完整张量或连续前缀，最终仍须完整 tensor 哈希/固定pin校验。prefix测试10项正常/-O通过，覆盖缺范围、重叠、截断、错hash、ETag/header漂移等。

只提交源代码、pins、hash、摘要；运行输出含权重、日志或本地路径，只保留本地。本包无 payload、NPZ、probe hex、signed redirect 或私人绝对路径。
