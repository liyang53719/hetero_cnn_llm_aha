# 20:33 Numerical8被Protocol7覆盖的真实时序证据

五块128 token完整原Chisel数值仍0/5，最终同刺激RTL未通过，固定4096完整block有效MAC80/90%未实测。原L0 head4 FAIL与1933预期顶层Numerical8的FAIL均保留；不重启未知旧Qwen2/L3完整profile。

## DONE：无侵入实际追踪
新增纯只读7phase trace；静态AST核删除观察调用后，cycle/settle/observations/drive/read与1833原驱动相同，不额外eval/clock，不写内部状态。4内部位置由同冻结LLVM精确GEP/load/store核验：Qwen2 status681496/i8、guard held status69162/i8及两个原predicate寄存器；数据偏移及源证据本地保存，不猜未证语义。
新独立synthetic首Norm Inf trace身份63479正常exit0，172周期、12次真实AR/R、无写。复用原libhost SHA6c7ec0a0437bfca256e8829d3a1c828b99beb55b41cc5f45cf7dbe1b74736e50及同17native，LLVM edfd1d4947f9c043f284c0e5992e678addfa77dac54c12e5bc29e2d85470f2b3未改，没有重编、精度或fatal策略变更。

## 实际内部传播
- 周期167 after_host_rise：标量策略error寄存器置1。
- 周期168：Qwen2内部status=Numerical8，resetRequired出现。
- 周期169：原guard覆盖predicate置1，held status=Protocol7。
- 周期171：顶层result有效且status7。
这证实原内部Numerical8确实产生并被guard覆盖7，1933差异不再只是源码解释。原期待顶层8的测试仍FAIL，不为迁就测试修改错误语义。边沿后公开组合输出可能尚未稳定，握手只按post_low_settled/pre-edge规则解释，不把短暂组合值当完成事件。

精确PASS仅内部8→7只读trace。合成输入只执行首Norm、读取x首64B，未完整RMS、未完成任何真实128-token block，strict exit86没有触发；不冒完整数值或利用率。

## ONGOING / TODO / 五块阻塞
Qwen2真实FP32新21-op布局、输入和AXI响应器已在，尚受未知旧任务并发限制不能launch完整profile；不把新身份改名当规避。0.8B L0/L3仍缺原hidden实体/生成者，L3原刺激身份亦缺；35B L0/L3完整真实payload仍缺且CDN拒绝未解除，不重复下载或候选搜索。四块没有本轮新增数值执行，明确不把检查当编码。
继续应以真实完整执行与原异常/数学契约为主；此轮只读观测解决具体错误归因，不宣称模型通过。最终模型通过后冻结同输入/参考/配置及源码，再同刺激RTL；统一4096硬件未按profile变化。

## 运行与清理
开工main cfb53090、同head CI43088956354成功，仅payload guard。原作业均已知本轮终态，旧未知会话不据当前/proc推断停止。工作树干净、约9.1GiB/56GiB可用，关键证据和库新hash复核，临时清单检查。既有数据清理0，唯一证据与运行依赖保留；发布仅允许中文摘要/hash，不上传源码、rawlog、权重或输出。
