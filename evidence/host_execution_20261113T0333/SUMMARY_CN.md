# 03:33 真实Host与iDMA闭包推进（完整prefill INCOMPLETE）

现场0233保留，先核main d80873be，CI43352975217 success仅payload。工作树干净，临时清单已核，清理0；旧未知Qwen2/L3 Host未重启。

核原身份后续终态：85317生成Host LLVM exit0，37902生成机器码exit0。40处同宽同序array兼容修复经fresh49152个实际编译差分通过，105原assert相同；19组C callback的零值/105失败位分别验证，但不是硬件时钟验证。Matrix5606、3060 exit0，8×512合计4096真实handle reset/idle/lifecycle通过，非数值。

本轮实质恢复iDMA原artifact12099239717，927源文件逐项SHA及原manifest a699b807…7b19匹配。唯一53486实际生成、make-j1、链接exit0，复用Matrix/ICG/Host成功对象不重编。

新联合driver绑定明确hash，比较整个Host状态和17路pending/snapshot低相位收敛，高相Host只eval一次，真实native clock后再低相位发布。2项人工failurehook通过：不收敛不clock，prepare失败不读旧snapshot。另完成真实17共享库（8Matrix+8ICG+1iDMA）注册和4周期reset/clock、冻结快照/坏位/缺sink永久poison测试，通过；不是占位callback。随后唯一真实Host联合链接（-zdefs）及12周期实跑exit0：4reset+8idle均收敛，PC/resetRequired/jobs/issues/DMAtransfer为0，AW/AR/W/result/completion均未激励。范围只限reset/idle，不是完整prefill；真实fatal先于外部提交仍未验证。

五块128完整原Chisel仍0/5，最终同刺激RTL与固定4096完整block有效MAC80/90%未测。原L0 head4 FAIL、35B两块完整权重缺失、MoE契约及未知旧Host边界保持。仅发布允许摘要/hash，源码/库/日志/数据留本地。
