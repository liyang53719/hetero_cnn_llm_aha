# 00:33 候选HWIR与真实输入读取闭包恢复（完整prefill INCOMPLETE）

核远端main020ef49a、CI43331115018 success，仅payload门禁。现场2333候选FIR保留，工作区干净，9.3GiB可用内存/57GiB磁盘，临时清单已核，清理0。旧Host会话终态仍未知，未重启，未继承已失去产物的PASS。

实做：复用现有firtool1.62.1，不下载重建工具；原lower会话18753 exit0，完整固定4096候选FIR成功生成真实HWIR。105条原断言降为105组sv.error/sv.fatal，另1条工具保留即时断言；Top仍8Matrix+8ICG+1DMA，countPolicy为i3加法。工具版本不同于失去的1.163 Arc闭包，未声称可互换；严格断言宏和真实native运行仍待接入。本轮只有lower/结构验证，无Arc执行、RTL仿真或数值PASS。

恢复Qwen2原21命令/215描述符，二进制hash匹配原pin。原C++ double trig重新生成cos/sin，两项冻结hash一致；13项raw核验，FP32展开/转置lazy映射全流与直接oracle一致，150项字节、行边界、越界检查通过。Qwen2原地址只读桥14段齐全；0.8B L0完整16段，L3的12段仍缺trig。桥9项测试及整rope读取通过，无中间参考预载；L0零尾明确为新padding身份，不继承历史通过。

新增17独占handle管理源码：全输入齐备后prepare、原子输出发布、错误后永久失效、冻结期拒绝新输入及低时钟结束。6项人工callback单测exit0，仅注册管理层资格；实际ABI解包、ICG驱动Matrix时钟和真实native库仍缺，不能冒17路硬件联合通过。

五块128完整原Chisel仍0/5，最终同刺激RTL及4096完整block有效MAC80/90%未测。原L0 head4 FAIL、35B两块完整权重缺失、旧Host并发边界均保持。下一步补L3原trig及匹配执行/native闭包；源码和数据只留本地，发布仅允许摘要/hash。
