# 16:33 原Host实际eval接通真实17（仅reset/idle，完整M128 INCOMPLETE）

main b0d877e7核验，CI43250101928 success仅payload门禁。原30869终态exit0由owner确认，现存结果hash重新匹配：SiLU25231360操作及两RMS末尾BF16转换的UF/NX核查完成，norm0/norm1/act逐位一致，247.62秒；不冒硬件传播通过。

本轮真实原Host编译IR实际eval接8Matrix+8ICG+1iDMA，4reset+8idle共12周期通过。前后低相完整Host状态及17输入/输出快照均2delta收敛，高相Host eval一次，真实ICG先于Matrix，native边沿后重新low settle发布状态。pc/resetRequired为0，无launch；不是完整profile，不是最终RTL回放。保留105strict，联合测试未实际触发数值fatal。

失败边界：真实Matrix非法reset宽度导致全注册表永久poison，其他ICG source exit87；诊断budget1未收敛时driver零clock；诊断非法drive时driver零clock且不copy旧快照。后两为Python测试hook，非真实数值fatal。活跃命令/握手和完整prefill仍未跑，不能由idle证明全部调度正确。

真实iDMA原库单64B对齐传输26周期通过，真实AR/R/AW/W/B，AR/AW/W反压、R延迟、完成保持4周期，数据/Wstrb/last一致且rsp_error0；不含多beat、非对齐、错误响应或完整Host资格。

新增真实Q投影301989888次逐FMA UF/NX核查45262 exit0/7.44秒，UF0/NX30017769，q0逐位对冻结一致。BF16乘积精确binary64、TwoSum残差与逐步FP32舍入，7个Fraction边界差分通过；仅Q有限FMA，其余Matrix阶段/硬件flags未全核。

输入侧串联原metadata、真实只读输入及scratch写后读/输出覆盖，7项三profile实际地址局部测试通过；未写字节拒绝，不补零或预装参考中间量。它不是AXI从机，实际AW/W配对、burst/tag/响应必须由driver保证。

五块128完整原Chisel仍0/5，最终同刺激RTL未过，固定4096完整block有效MAC80/90%未测。L0原head4 FAIL保留，35B两块仍缺完整训练权重，不绕限制；未知旧Host未重启。下一步真实AXI内存接入及活跃受限握手验证，不能用局部通过冒完整数值。当前任务均终态无在途长测。工作树干净，临时清单已核，清理0；只发布允许摘要/hash，其余本地保留。
