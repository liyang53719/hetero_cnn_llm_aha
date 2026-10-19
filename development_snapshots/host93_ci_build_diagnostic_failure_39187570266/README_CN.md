# 第二次 CI 构建诊断实际失败（原始安全证据）

Actions run 39187570266，attempt 1，commit `5f75602a5b5ea8f85c34d8df4b67f256b4a4a7ef`，结果 failure。本目录三 JSON 与下载的安全 artifact 原字节一致；本次实际独审身份待封，不能把作者摘录当独审。

前 13 个阶段为 EXIT0_CLEANED。fresh_make 在 62.251071 秒返回 exit_code=2，原 WNOWAIT code=1/status=2，receipt_timed_out=false，cleanup_confirmed=true。原先观察到的是进程正常退出码 2；后续清理 kill 不能作为此退出的原因。failure_boundary=NATIVE_SUPERVISION、failure_code=CHILD_EXIT_NONZERO。

观察到 RUSAGE_CHILDREN user CPU=60.802876 秒、system CPU=1.282175 秒；maxrss=616720 KiB 是此协调进程所收子进程的累计峰值，不是 fresh_make 阶段专属或瞬时内存。整个协调序列73.883024秒。

有限分类过滤器未输出任何识别行：observations=[]、merged_log_tail=""、truncated=false。这不证明合并编译日志没有报错；未知格式原来按整行丢弃，且收集异常也会产生空默认诊断。原 native.log 仅保存在已结束的 runner 私有目录，当前未取得。因此不能确定具体 make、编译器、生成脚本错误，更不能推断 OOM。

所有新 toolchain / tiny / Host / N0 / weights scope 均为 false；后续阶段未执行。原第一次 run39185138343仍FAIL，结果不倒填。无自动重试；下一诊断更改须独立 SOURCE 审核后另获一次执行安排。
