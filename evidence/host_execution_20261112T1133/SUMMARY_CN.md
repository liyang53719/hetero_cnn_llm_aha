# 11:33 严格适配实作、精确参考加速及native依赖推进

1033仍在，未重复lower。新strict适配将105真实断言的predicate/enable/clock提取为19组DPI，原sv.assert保留；ifdef/else包围assert一律拒绝，真实断言不受只管消息的PRINTF/SYNTHESIS门控制。实际Arc→LLVM隔离运行16组!held||intent、reset/enable组合，正常exit0、故障exit86，低相/重复高相不多发callback。仅隔离cone；整Host适配IR尚未解析编译、原消息逐条绑定和跨组同时失败顺序未证明，不能算Host strict通过。

QK/PV精确加速接21步参考，仅并行独立输出，保原16-lane累加/归约/缩放与PV升序key。M8全量Fraction逐位一致，8边界通过；合成M128双头及完整累加链抽样通过，不能当五块通过。新真实参考72018预算300CPU秒/2GiB在途，快照0–15共16阶段已写receipt，正在gate；没有继承丢失27005产物。flags未全审计、非Host。

官方Verilator5.032-1+b2包精确历史SHA恢复，初次URL404经同官方目录纠正，非访问拒绝。原FMA emitter首次因旧工具路径Permission denied失败，未改权限；显式选择已验firtool1.163后28227 exit0/2.29秒，生成原HeteroBF16FmaLane.sv SHA72d8f4dd98fcfd46e62e2cadc5087d4bbca2aaf3c085bd7fe171a390a133a5c3，5bit flags保留。仅lane生成，非数值等价或完整17native。

上游/项目路径审计：官方有64行chunk prefill；M1限制是旧GdnInputPrepOwner，不是上游整体。当前RawPrep/入口接受M128，每头两个64行chunk，非两个M1循环。历史已准入head4 phase7 FAIL应属数值执行错误。新增身份绑定故障定位工具5测试通过（合成身份，不冒Host采集），原FAIL不变。

五块完整M128原Chisel仍0/5；同刺激RTL未过、4096完整block有效MAC80/90%未测。未知旧Host不重启、35B限制不绕过。后续沿原72018收终态，补整Host严格适配和17native真实闭包。开工main923c967a，CI43202799538success仅Git门禁。工作树干净，临时清单保存、清理0。仅允许摘要/hash发布，不上传源码/IR/日志/权重/生成数据。
