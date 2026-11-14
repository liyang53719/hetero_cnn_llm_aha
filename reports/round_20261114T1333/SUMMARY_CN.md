# 2026-11-14 13:33 执行闭包与严格异常（INCOMPLETE/编译有界超时）
## 真native及共享绑定代码
原14897真实iDMA生成/单线程编译/链接exit0（2.33/16.09/7.26秒），93500接口reset-idle及非法输入/无效状态测试exit0；finish为test-only注入，不冒RTL fatal。库SHA33c0075b172105d7a6361b97023a6f5678e915f65f3ad299318601690a35e6d4。
4个原FMA载体20241 compile/emit成功；Matrix原10361生成exit0/30.14秒，185 C++文件，单线程make仍在途，未重复。单端点512MAC，整机8独立实例才4096，未用512替整机。
新actual_leaves/registry对象按真实Matrix37/521、ICG、DMA17/25 ABI映射，Wall/Wextra/Werror编译成功；低拍prepare数据冻结、高拍ICG到对应Matrix再DMA、错误poison的协调源码已写。因Matrix库未到，尚未真实17链接/时钟运行，不冒shared17通过。
## Arc实际失败及保留严格语义的修复候选
原26468完整编译明确失败：官方sim.clocked_terminate组合condition未lower；微型复现也失败，保留记录。没有删除断言。新106站clocked strict_fatal(site,condition)回调保留原条件与clock，site表冻结。
微型真实Arc已编译执行：低拍不触发、reset抑制、同高电平不重复、下一正沿错误abort，正/负进程退出0/-6；仅微型边沿/条件资格，非完整Host异常优先级。
新完整候选原39875编译达到150秒上限而停止，无有效LLVM输出、无Host运行；未盲目重跑。下一应分阶段诊断Arc耗时，不把preproc当编译成功。prepared_callbacks SHA d7af99c7570ab3950f7d9963584d55283ce4c1e812c8a2bfea7337bd2523487b，所有源/失败日志保留本地。
## 数值接入代码
新增实际B ACK提交策略的Qwen2首RMS捕获器，核原manifest/完整FP32参考hash；W暂存，只有匹配B OKAY握手才提交。16项合成协议测试通过，限定单outstanding、64B INCR，非法ID/响应/WLAST/strobe/越界等拒绝并poison。未发生真实Host交易，不预填输出，不冒数值终态。
## 五块与维护
五块完整M128原Chisel仍0/5，同4096统一硬件要求保持；完整RTL及全blockMAC利用率未测。旧37765终态未知，未重启，丢失50行不继承。L0 strict FAIL、35B真实权重/冻结runtime与MoE契约阻塞保持。
基线main6731e687af03c5576f0a99d93182379c99a9426e、CI43596431626 success仅payload守卫；工作树clean，临时清单已核清理0。仅发布允许摘要/计划，代码数据证据本地保存。
