# FAIL：固定头获取与编译已返回，configure 后合同未闭合

- GitHub Actions：39193914902，attempt 1，提交 89f8a9aa9378d341242dc0b0a03750070fba756f，job 117872419846。
- 单次完整 Host 恢复 job 已失败；三份原始安全 JSON 原字节保存于本目录。协调器记录总耗时 11.513972 秒。
- 已记录的 15 个子阶段均 exit 0，且 cleanup_confirmed=true。固定头获取 0.156121 秒；真实 g++ 头文件对象编译 1.443194 秒。后续 autoconf 0.254950 秒，configure 5.187258 秒。
- 固定源码控制流表明：能进入 autoconf/configure，意味着头 SHA、单成员收据及编译依赖文件对精确私有头路径的检查已返回；这些是控制流限定证据，未上传私有头文件、对象或依赖文件。
- configure 子进程成功之后、fresh_make 启动之前，Python 合同检查失败，summary 保留 INPUT_OR_CONTRACT。本次没有保存具体后验错误码，不能把某个候选代码缺陷说成已实测触发点。
- 原 source 文本中的配置行整行比较不能接受合法尾空格，是后续可用固定官方源码及小 fixture 单独验证的候选问题；该推导不改写此次失败记录。
- 本轮没有执行 fresh_make、派生工具微例或 Host 生成/编译/reset/launch；8 项最终 scope 均 false。
- CPU 数字是阶段前后子进程计数差值；RSS 是本协调器累计 child 峰值，不能解释为各阶段独立峰。
- 实际独审：PENDING_AT_SUMMARY_CREATION。原先三次失败仍保留，未推断它们同因。

本目录只含安全摘要及公开来源 hash，不含包体、头文件正文、生成物、原始日志或机器路径。
