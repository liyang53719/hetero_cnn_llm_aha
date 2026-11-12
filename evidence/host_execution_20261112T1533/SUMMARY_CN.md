# 15:33 真实17 native接入、失败失效修复与取指桥（完整prefill INCOMPLETE）

开工main3cc38031，CI43238941155 success仅payload门禁。现场闭包保留，工作树干净，9.3GiB可用内存/56GiB磁盘；临时清单核查，清理0。

新增shared17真实接入8Matrix+8ICG+1iDMA。用本轮修复后的三库重新链接并重测32cycle，实际ICG控制各Matrix16正/负沿，冻结后输入变化不改变当前native边沿，重复rise及冻结期prepare拒绝。reset bootstrap来自真实drive/eval/read，不替换零输出。仅真实17局部reset/idle/clock，未调用Host eval；全Host组合fixedpoint、活跃握手、postedge状态发布排程仍未实现/证明，不能排除一拍滞后，strict callback未在联合测试触发。

iDMA原生成对象编译链接及生命周期、clock/reset、ABI负测通过，未测真实DMA传输。审计发现Matrix/ICG gotFinish失败后evaluated仍true，已修复为失败使快照失效；独立测试注入VerilatedContext.gotFinish后eval=-3、read/clock=-2。生产库无probe入口，原库保留；新库实际8Matrix/8ICG有限边界重测通过。39265/28643/24590均exit0。这不是实际RTL fatal触发资格。

修复实际Host取指缺口：旧输入桥只映射张量，漏命令/descriptor。新增原地址metadata读取，核验三profile合计178主TypedTensor根的地址、dtype、rank、shape、stride，4读取/边界/禁写测试通过。0.8B元数据尾零padding显式作为新总线映射身份，不冒旧hash恢复。未预装参考中间量。

Qwen2剩余SiLU及RMS末尾BF16转换flags审计原30869仍在途，300CPU秒/2GiB预算，本轮快照尚无阶段receipt，标INCOMPLETE；不推定通过，不重复前缀或重启该任务。

五块M128完整原Chisel仍0/5，同刺激最终RTL未过，固定4096完整block有效MAC80/90%未测。Qwen2/0.8B L3待真实完整执行，L0原head4 underflow FAIL保留，35B两块缺完整权重且不绕受限下载；未知旧完整Host未重启。下一步完成Host fixedpoint和严格异常调度，继续原30869取终态。只发布允许摘要/hash，源码、库、IR、权重与原日志本地保留。
