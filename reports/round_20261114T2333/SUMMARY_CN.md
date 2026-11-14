# 2026-11-14 23:33 hetero进展（INCOMPLETE）
- 现场：main基线6e6fcd9，CI43649576243成功，仅载荷门禁。工作树干净、约9GiB可用内存/53GiB磁盘；临时清单已核，清理0，旧37765未知未重启。
- 真实Host活跃链：复用2233精确新对象/真实17，原24835 exit0。439周期/1.347秒，一次合法launch，15个AXI读beat，其中4个为原Qwen2 FP32 x真实256B；精确地址及hash保存。成功Host/native高低沿后才提交preedge快照。PC0/resetRequired0，无写回/completion；非首RMS数值通过、非checkpoint。
- harness修复：初版9920将metadata误计tensor，49周期原结果保留并纠正；新判据用x精确地址。不是硬件变化，不把metadata称真实输入。
- L0完整M128 NormC2 BF16独立参考重新计算83325e03bb7c66b6fec50a16a514d59ca25075a4fe318c8ef0adff05ee94a5f3，与原可用输出逐字节一致；16项ACK捕获合成测试通过。
- 重要算术/调度语义：原RMS owner将输出每行首128B暂存32个FP32 residue后覆盖BF16。捕获分离raw ACK诊断和final比较，缺owner completion为NOT_EVALUATED，不能仅完整掩码或partial mismatch判最终PASS/FAIL。保每次ACK证据，新增6项覆盖合成测试通过。
- 恢复闭包：真实ICG新--savable库91520构建成功，freshprocess非零latch/edge计数后8观测相等，6类损坏/版本/非法时刻负例拒绝。仅ICG，不是全Host恢复。
- 在途：Matrix原79805生成exit0/28.49s、185个C++，make-j1在途；DMA原90385启动，记录PGID并timeout killpg/wait。旧make父超时风险已明确，不能不核孙进程就重试。独立新目录不覆盖生产库，Matrix最终需完整依赖pin后重链接。共享17 registry/所有handle/AXI/Host尚待完整保存和差分。
- 五块128完整原Chisel0/5，固定4096，完整RTL/全block MAC利用率未测。0.8B L0/L3首RMS输入/输出桥资格只限参考与合成协议；35B完整权重/原准入缺失，L0 strict FAIL及MoE同分契约未改变。
- 下一：沿79805/90385原身份收结果，补真实Matrix/DMA与共享17恢复，再接新Host活跃状态的freshprocess轨迹差分；不启动丢状态的长RMS重复前缀。
