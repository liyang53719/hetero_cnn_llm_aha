# 11:33 原Host分段推进与吞吐修复（INCOMPLETE）

原84795新独立有界首RMS会话实际推进至2400周期：两段各1200周期，16.8846秒，35读beat含24×64B真实FP32输入。两暂停边界均低相、无pending、无读写请求valid，pc0/jobs1/resetRequired0，完整Host+17观察值暂停前后相同，未重建handle/reset。会话暂留内存等待，30分钟无续令自动关闭；不是持久checkpoint，进程/环境丢失无法恢复，不可假定下一小时可续。

现有native未启savable，单独保存Host会漏17模型/context/shared状态/AXI，禁止冒完整恢复。未重启旧未知Host。

性能实质调查：eval含65509静态调用，其中26395及2417次两类函数仅纯整数select/ret。正在准备精确类型匹配局部内联候选，保留原LLVM/库及所有clock/strict，不重复历史全O1超时路径。优化未通过前不替换原活进程。

首RMS对照契约按原源码核定scalar/memory/format/ACK计数，7合成测试通过。当前外部IO不导出完整receipt，不得用caller布尔或替代计数冒终态；未收到首算子数值输出。

五块128完整原Chisel数值仍0/5；35B权重缺失及原underflow FAIL不变，完整RTL与有效MAC利用率未测。工作树干净，临时清单已核、清理0。基线a64fd599 CI43409738708 success仅payload guard。源码保留本地，未上传被拒源码或权重。
