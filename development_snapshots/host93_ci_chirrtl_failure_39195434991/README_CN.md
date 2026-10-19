# 部分 PASS / 整体 FAIL：新工具链与双 handle 微例完成，CHIRRTL 子进程失败

- GitHub Actions 39195434991，attempt 1，提交 4a4c8729d39873c0710c80b36daa9091496e5edb，job 117877080256。本目录三份安全 JSON 按原字节保存。
- 协调器总记录 609.431408 秒；26 个阶段中前 25 个 exit 0 且已确认清理。最后 host93_chirrtl 自然 exit 1，waitid code/status 为 1/1，receipt_timed_out=false，cleanup_confirmed=true，耗时 14.112065 秒。
- toolchain 组件已经完整返回，summary 的 toolchain_build、toolchain_tiny 两项为 true，completed_components=[toolchain]。这表示本轮已重新通过工具构建及固定派生双 handle 微例的同 job 门；不继承已丢失的历史二进制。
- Host93 的 Java 版本、87 JAR 获取、20 HardFloat 源获取、93 源组装和 CLASS 阶段均返回成功。CLASS 子进程耗时 85.110954 秒；进入 CHIRRTL 的控制流意味着其前置 class/JAR/source 后验已返回，但本安全包没有私有文件正文供独立重哈希。
- CHIRRTL 失败行明确 NATIVE_SUPERVISION / CHILD_EXIT_NONZERO。旧诊断策略只收集 fresh_make 的文本尾，因此本阶段 context_state=NOT_COLLECTED；summary 的 UNREPORTED/UNMAPPED_CONTRACT 不提供额外根因。当前不能推断 OOM、时限、缺失依赖或设计错误。
- 后继需要统一收集所有失败子阶段的有界去敏日志；本次不补写不存在的诊断，也不改写前四轮失败。
- fresh_host_sv、cpp_generated、cpp_compiled、reset_launch、n0_numeric、weights_loaded 六项仍 false。没有工具之外的 Host 数值或 RTL 回放资格。
- CPU 是阶段前后子进程累计计数差值；RSS 是该协调器累计 child 峰，不作单阶段独立峰值。
- 实际独审身份：PENDING_AT_SUMMARY_CREATION。

只保存公开源码身份与安全摘要，不含工具二进制、模型/张量、生成源码、原日志或机器路径。
