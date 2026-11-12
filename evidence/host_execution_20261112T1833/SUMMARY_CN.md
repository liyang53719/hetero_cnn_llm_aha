# 18:33 必要执行闭包重建与真实输入恢复（完整prefill INCOMPLETE）

开工main031f8eb3、CI43271235022 success仅payload门禁；1733源码修复仍在。官方1.163精确143MB工具重新校验恢复，复用原FIR直接lower，57636 exit0/47.42秒，HWIR精确重现ebd1c5f7894381dbee534fda37e3ae3a48286d9ac901b3e1ceb93b6a64dbdfbb，实际105sv.assert新计数确认，无重复Scala。

新增strict适配源码识别105断言/19clock组/17extern，保留原assert并携带所有sv.if enable。首次71334类型失败保日志，显式seq.to_clock后46801仍exit1：通过类型门但实际Arc遇Matrix needsClock/ICG反馈SCC，无LLVM/object。5项新适配器测试通过，未继承旧运行资格；下一步恢复真实同handle sink/source+fixedpoint，不能常量ready消环。精确printf消息及跨组顺序仍未证明。

native原49918在途：官方Verilator包及iDMA原artifact恢复927源逐SHA通过；仅新编四段emitter复用原classes，四段FMA生成、ICG生成/编译/链接、iDMA生成/编译/链接均exit0，尚无运行重测。Matrix生成exit0/29.97秒，185C++单线程编译在途，240秒预算；生成分块选项不同导致文件数不同，非缩硬件。1733gotFinish修复及初始化final守护并入候选；旧未知完整Host不重启。

三profile原metadata六个二进制精确匹配历史pin：Qwen2命令21/descriptor215，L0 17/219，L3 22/261，取指边界5测试通过。继续新增真实raw惰性读取：Qwen2 13段按原FP32升精度/转置，缺rope；L0完整16段含原hidden/AB/冷状态；L3 12段缺trig。每映射与独立NumPy逐字节采样比较及4测试通过。0.8B总线尾零padding显式新映射身份，不预装参考中间量，35B限制不绕。

重新实现独立参考QK/PV原序加速，fresh M8/HD128全输出对原Fraction逐位一致，8边界测试通过。新唯一73678执行真实21步参考，300CPU秒/2GiB/360秒wall预算；快照已到up阶段，完整终态待原身份核实，不继承丢失的21步/flags PASS，无Host。

五块128完整原Chisel仍0/5，同刺激最终RTL未过，固定4096完整block有效MAC80/90%未测；L0原head4 FAIL保留。主要阻塞是Host反馈边界与执行闭包未全恢复、35B完整权重缺失、未知旧Host不能重启。清单已核、工作树干净、清理0。仅允许摘要/hash发布，源码/库/IR/权重及原日志本地保留。
