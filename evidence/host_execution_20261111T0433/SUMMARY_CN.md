# 04:33 独立工程推进；完整数值INCOMPLETE

## 旧任务身份及约束
main9852b76d、CI42958003891 success已核。原L3 3321仍Unknown，旧两日志仍停03:48:31/30，没有新提交凭证。本轮没有启动L3/Qwen2恢复，也未终止未知旧任务。已验可恢复状态仍为L3 864911和Qwen2 325000；旧进程终态缺证，不用新PID视图或名义timeout代替确认。

## L0后续真实布局回归
新增本地rank3 typed记录/物理scratch测试，直接解码原profile1/3 emitter记录，对照原GdnChunkAddressPlan全部head和两个64-token chunk的24个中间矩阵。7项测试普通/-O均通过，覆盖坏stride、错误head、rank2超范围拒绝；L0完整scratch26,869,760B覆盖、无RawPrep/Chunk等输出预装。35B对应32head布局53,739,520B仅运行时内存几何，不冒固定片上缓存或硬件容量通过。
当前原Host明确需真实Conv/AB提交后RawPrep才live，Chunk需prep/conv/冷state与fresh scratch，再由实际Chunk/Z喂GatedNorm。未找出可跳过依赖的合法捷径，未改数学/fatal。原L0 head4/chunk0/phase7 tiny+inexact下溢FAIL保留。当前未实际跑到Chunk，本测试只是布局回归，不是模型或RTL数值。

## 真实L3后程stalls归因
pipelineStalls的原定义仅step.valid && work && !step.ready，不等于所有无issue周期。已保存日志：前80行5context的81920次wide issue时stalls0；尾48行变3context，每N组3×1024=3072 issue后stalls增1920，连续8组平台值1920至15360与源码推导一致。原同context需先retire，5拍归还约束下3context每K16产生30bubble，64块得1920。
这是原源码+保存模型执行日志的一致证据，无新Host/native运行。历史telemetry缺ready/credit/occupancy分项，不能称逐周期唯一归因。尾tile跨N组有序重叠可作为后续候选，但需核accumulator/tag/credit资源和原归约次序，不能假设额外资源免费，更不能只改bank ready冒实现。完整block分母尚不存在，不能由这些计数宣称80%/90%达标。

## 监督可靠性候选代码
本地实作共享flock、不可变身份、原子heartbeat/终态、同键重复拒绝、边界停止和guardian。7项dummy生命周期测试通过，另孤儿后代测试通过：父监督进程崩溃或segment父退出时，guardian持锁至同进程组后代结束。
审查中补实际缺口：逐段独立校验不足以防错误合法组，已加入显式epoch/pin/profile/work_key一致、周期严格前进、双源manifest/receipt SHA链；8项错误身份/周期/来源链负测通过。无prior真实任务拒绝，禁止隐式迁移。
候选未接生产，无新真实DUT资格。新锁不能排除旧无锁任务，也不能保证不共享文件系统或逃逸进程组的互斥；不是当前重启许可。所有dummy测试结束，无残留测试任务。

## 五块及计划
五块128 token完整数值仍0/5；本轮未增加完整数值PASS。Qwen2/L3已提交子集数值保留原范围，L0旧下溢FAIL保留，35B缺真实完整权重仍阻塞。固定4096同硬件、原FP32/BF16顺序和fatal不变，最终同刺激RTL回放未通过。
DONE：L0布局回归、尾tile计数归因、监督候选及负测。TODO：旧执行终态/恢复决定明确后才接入可靠监督并从各自已验receipt继续；新共享架构需五块重测。
开始全round43877项约11.0GB，约9GiB可用内存/47GiB磁盘。本轮没有删除、上传权重/NPZ、改运行源码或重启旧任务。只发布允许摘要和hash，候选源及原日志本地保留。

离线计数工具另有30项单测通过：单日志/跨段计数回退与reset拒绝、截断/缺字段/非法与重复字段、3/5context及K边界。原5份日志严格解析后8组计数关系仍一致。
