# Owner 局部生成后验失败：安全实际摘要

本轮原 session 42131 已结束。generation 子进程自然退出 0，用时 153.944213 秒，清理确认、未超时；完整生成日志 census 的 warning/error/unparsed header 均为 0。随后 Python 生成后验抛出 ValueError（small read bound），outer 退出 1，用时 155.54876243299805 秒。原 EXECUTION_RESULT.status 为 INCOMPLETE；生成进程成功不能充当整个 owner 测试成功。

## 已定位的停止边界

调用方读取 VQwenOwnerKernel___024root.h 时给 generated_text 的上限为 16 MiB，但该函数内部调用的 small_read 仍固定最多 4 MiB。实际 root header 为 4,630,258 字节（SHA-256 a9371ed20684a6b5635de6203918cd33b910d856bd83618cf4a33c9dda398aaf），超过 4,194,304 字节；原 traceback 与已发布源码共同定位到该读取边界。此处保存原 failure_code/failure_boundary 的 null，不给原 receipt 倒填新失败码。

生成 census 的另一个有界 reader 曾成功重读该 header；其 cluster_structure 仍未建立、root_header_state 为 UNRECOGNIZED_SYNTAX。这个独立读取记录不能替代后来失败的 reader，也不能授予新 top 的层级/ABI 资格。95 个观察字段检查未完成，196 端口及 cluster witness 未进入；compile 与 owner native run 均未 START。

## 资格边界

没有 owner 合法 job、partial/window 退休或 12801 issue 目标的实际观测，也没有本轮 owner 故障重现证据。原 Host 两轮失败及上游原因未明的结论保留；本轮工具后验失败不能证明或否定它们。full_job/full_block 为 false，五 block 仍 0/5；historical_host_failure_reproduced、official/application/typed-to-RTL 资格均为 null。

本轮开始时执行来源已发布在 8b963f58f86d156d4587654b199054f5e09e4fec。七件原证据的 manifest 为 959 字节 / cecf9a7c0da9c2674198ae18992855afa660d546dc0ec24a7542552d7838a5da。冻结 inventory 记录 536 项，528 个普通文件、8 个目录、普通文件共 80,670,440 字节。正式 actual 独审已接受此有限范围：review_owner_micro_generation_actual_20261019T2322，MANIFEST 282 B / d8a40602b4d5a500801f374ec93efc5be7b455fd87ae2a12ab07b01a205c6828；SUMMARY.md 4666 B / c2816c97363998f17e782f19245051cf507f45a8b98543302998cea2438e33ee；verdict ACCEPT_ACTUAL_OWNER_GENERATION_NATURAL_ZERO_POSTFLIGHT_HEADER_BOUND_FAILURE_ONLY。

独审逐项重核 7 件原证据、536 项当前树、39 件源码包成员、7 件 staged owner 原件及 338 件原始源输入（79,657,058 字节）。现物闭合只授有限生成缓存来源资格，不授可搬迁、可编译、ABI 或 runtime 成功；工具/系统依赖与资源准入仍由后继实际入口独立把关。

本批仅安全数字、公开来源身份和完整中文计划后继；原日志、机器路径、数组与二进制均不公开。没有重跑生成、编译、RTL 或测试，没有改原 FAIL；后续 cache/read-bound 修复须独立审查。不触发新的 Host/RTL/native 作业；workflow 文件不变，普通 push 的轻量 guard 另记。
