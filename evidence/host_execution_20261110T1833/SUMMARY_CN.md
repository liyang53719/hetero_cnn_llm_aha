# hetero 18:33：严格保护修复候选与17native真实边界（INCOMPLETE）

## 本轮实际编码和执行
- 实现限定形式的strict assertion IR桥：原107条posedge i1断言的predicate、enable、clock不变，通过官方有时钟DPI调用仅做诊断与失败终止，不替代DUT算术、不增加物理端口。8场景实际LLVM执行通过，坏条件exit1、reset屏蔽、重复高不重触发；两断言+原print组合也实际执行，任一失败终止，本小例保留print/首错顺序。原默认Arc丢断言FAIL保留。
- 完整迁移发现root module带attributes时漏插声明，已修复并加正反测试。全107条覆盖、模块物理header不变，仅Arc-conv编译通过。协调延迟产生一次6.44秒重复轻量arc-conv，两次均终态，未重复长Host。
- 唯一完整LLVM编译以180秒/7GiB预算启动，7.69秒exit1（非超时）：loop splitting did not eliminate all loops。具体链路MatrixPipelineService聚合控制→ICG enable/clock→Matrix extern→tags/ready反馈。原RTL诊断确认本报告路径的clock→out_valid边是extern保守伪组合依赖：out_valid来自active_q及队列/令牌寄存状态。但step_ready确实依赖当前context/out_ready，不能把所有输出一律当无依赖；尚未完成有证据的边界修复。未删控制/加硬件延迟绕过，尚无完整编译后Host执行。
- 原端口8Matrix+8ICG+1iDMA（4096MAC）显式Arc state-slot边界真实执行：400半周期、1,667,200个Matrix输出word与独立真实ABI逐项一致；8slice各1输出/1completion，真实门控时钟、重复高、稳定点和非法帧错误传播通过。iDMA真实请求接受/busy/背压后reset对照通过，不宣称DMA完成。LLVM不自动调用DLL，外部适配显式驱动真实库；此边界结果不等于完整Host调度或block数值。
- 提取原SharedL2Fabric实际模块，保留字节掩码/同步内存/仲裁逻辑，用有明确同步reset类型的测试外围完成compiled IR执行：64写、48读、2048字节掩码结果、96背压周期、重复高及非法地址sticky/reset均通过。原模块无断言；此项仅局部内存后端验证。

## 五块和最终目标
五块M128完整数值仍0/5；Qwen2原FP32全链未完成，0.8B L0原underflow FAIL保留、L3真实owner/receipt未完整执行，35B L0/L3真实冻结输入与MoE同分契约缺口仍在。固定4096资源不减，候选模拟桥不改原Chisel算术、舍入或物理接口。最终同一份RTL完整数值和80%/90%利用率目标未变化，本轮无完整block周期/利用率实测。

下一步沿本次原失败身份诊断extern时钟反馈依赖，验证不改硬件时序的模拟边界拆分；完整107断言/print/多实例及错误传播必须联合验证，然后才接真实M128输入。不得直接采用会丢保护的默认Arc路径。

## 发布与清理
只发布摘要/hash。候选源码、IR、工具、rawlogs、权重/NPZ均未上传，不绕此前审查拒绝。临时数据保留唯一证据，本轮无清理。所有已列执行作业均终态。
