# hetero 23:33：持续任务异常归因与独立修复候选（INCOMPLETE）

## 原任务实际状态及纠正
先核main8d5659f与CI42917266329 success，仅payload guard。最初读到1440秒共享心跳时只获得最后保存状态；随后原worker本线程poll48108也返回Unknown，日志mtime停23:05:23（driver最后约23:05:33），无L3_RESULT/SUPERVISOR_RESULT。只读打开原两锁并非阻塞flock都可取得且立即释放，代码规定锁持续至进程结束，因此原runner/supervisor不再保持存活身份。不是单纯跨线程Unknown，也不是正常结束或6小时预算到期；未取得exitcode/终止原因，不能推定OOM或平台超时。
没有重启、终止原任务或覆盖证据。当前cloud连接只说明现在可用，不证明旧作业生命周期；没有能找回旧session终态的工具。同执行环境内supervisor不能覆盖执行环境整体失去运行身份。停止原因仍UNKNOWN；在持久生命周期或完整checkpoint验证前不重复昂贵前缀。

## 已保留的真实数值与进度
最后保存1440秒：1742380帧、pc1、completed1/jobs2、DMA43831、Matrix pipelineIssues66560、resetRequired0；后续driver日志还略有推进，但无Q Dense完成actual。当前run首Norm实际262144字节再次与独立参考全同，SHA ab1f29183a7fe678d9dcbd87cc7bc680db323bd75ec7a839ab154a2e41e7fab9。精确PASS仍仅L3 M128首Norm，不是Dense、完整22命令block、五块或最终RTL。五块完整数值仍0/5。

## 独立AXI供数审计与代码
当前实际weightReadBeats=16；原RetainedIdmaWeightBurstAdapter仅maxBeats>16才安装4-entry read segments，当前不存在该队列。实际硬件只在idle接新request，req.write选择单方向，直到done/reply才接下一请求。driver虽另有R/B串行限制，但不能把此前约46%的理想上界全归咎driver，或靠被动模型直接解锁硬件多outstanding/读写重叠。源硬件还存在权重重读和单request约束。
新建独立被动AXI队列候选，只响应实际请求，不执行DUT算术，不接运行driver；测试AW/W偏斜、R/B并发、背压稳定、写mask、地址hazard/同ID顺序/错误拒绝。其协议资格不冒当前硬件性能、数值或80%/90%利用率达标。当前供数/源码上界与最终目标内存及RTL实测仍分开。

## 约束与保存
保留4096和同一硬件定义、原FP32/BF16舍入、fatal和原L0 underflow FAIL；不以阶段参考灌入恢复状态。Qwen2与L0准备工作保留，35B权重/契约缺口未绕过。仅允许摘要/hash发布，候选代码/原始日志/权重本地保留；临时清单无清理，唯一中断证据保留。

## 完整checkpoint实质可行性验证与缺口
审计确认现Matrix/ICG/iDMA三类生成模型均未启用savable，原ABI无save/restore；不能memcpy含指针对象、只保存公开输出或把参考中间值灌入恢复。独立以完全相同tc_clk.sv与参数仅加官方--savable生成选项重编真实ICG，保存/恢复实际内部latch与context，3个高/低cutpoint后1435次观察与不中断模型完全一致。初始探针在线程初始化次序上失败，修复测试构造后通过，未改DUT。**PASS仅ICG保存机制可行性，不是17native或完整checkpoint**。
已列完整实现缺口：Host全部state、8Matrix/8ICG/1iDMA全私有状态及wrapper clock/edge保护、fast适配器level/previous、driver DDR有效mask和AXI队列/计数/观察标记、transport序号/半帧屏障及所有pin必须同epoch。当前不具备完整恢复；下一步补齐且跨进程逐帧差分验证，再恢复长链，避免再丢失昂贵前缀。
