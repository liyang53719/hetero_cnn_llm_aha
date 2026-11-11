# 21:33 Guard错误优先级审计与原因保留候选

五块128 token完整原Chisel数值仍0/5，最终同刺激RTL未通过，4096完整block有效MAC80/90%未实测。原L0 head4 FAIL、1933预期顶层Numerical8的FAIL保留；2033内部8→Protocol7实测解释不变。不重启未知旧完整Host。

## 审计：不能直接把7改成8
globalFault混合owner.resetRequired与传输/控制故障，历史poison亦失去来源。即使physical status是Numerical8，同拍独立hard fault或历史fault仍必须保持Protocol优先。原physicalDone.ready在global/authority fault下可以接收，而wrong-tag/context/unsolicited等拒收。因此按physical.status!=OK简单绕覆盖会掩盖真正协议故障，不是安全修复。

## 实际局部候选编码与验证
最小候选保留全部原status优先级、ready、quarantine、poison、reset及原输出，仅增加11bit锁存：8bit原physical status+3bit当拍override输入（authority/global/poison）。causeValid由report组合译码，在matching physicalDone.fire捕获，背压期间保持、retire失效、reset清零。不是完整根因追踪，晚fault不改已锁存原因。
原Guard与候选双实例真实Chisel→HWIR→LLVM→机器码执行，23场景原输出逐边沿一致：clean0/3/4/8、同拍global/authority、历史poison、错误tag/context/unsolicited、反压、晚fault、消费与reset。独立审查机械去除8行新增和类重命名后原类体一致；额外准备19项接口向量。原emitter import遮蔽编译FAIL保留，修限定名后59837 exit0，测试exit0。
候选源码SHA908b32f2a866dd945712ea50abf44819da084a32d9ed02151e684888f9210b88；原Guard SHA4680762977b005951751f77b4d3b9fc3ef2dd24143374ee20c7e47c241361e53。
精确状态CANDIDATE_CAUSE_SIDEBAND_GUARD_PAIR_PASS_NOT_INTEGRATED。这是诊断原因保留，不是顶层7→8语义修复。没有修改精度或MAC，局部guard不是完整4096 Host资格；未接入Host/public ABI，phase预约/phaseDone活动分支未测。如将来接入统一定义，五块均须重新验证，不能迁移旧PASS。

## ONGOING / TODO / 五块
Qwen2真实FP32新21-op输入绑定及driver仍在，但完整launch受未知旧任务并发边界限制；0.8B两层缺原hidden/生成者及L3旧身份，35B两层完整payload缺且CDN拒绝未解除。本轮没有其他四块数值执行或新输入恢复，不把检查冒编码。strict fatal实际触发仍未完成。
下一步先补候选未测的phase路径与接线决策，不扩大diagnostic mask含义；主目标仍原完整模型数值后同刺激RTL。避免仅加边带无限替代真实prefill进展。

## 身份、CI和清理
开工main6ecfc61c，CI43097456849仍queued，未重跑或宣称通过。工作树干净、约9.1GiB内存/56GiB磁盘可用，临时清单检查，既有数据清理0。本轮59837已终态，没有新增运行作业。发布仅允许摘要/hash，不上传候选源码、rawlog、权重或输出。
