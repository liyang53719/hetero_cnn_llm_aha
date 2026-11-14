# 2026-11-14 21:33 hetero 进展（INCOMPLETE）
- 现场：远端基线2008b6b，CI43639203349成功，仅载荷门禁。本地源工作树干净；旧37765终态仍未知，未重启。
- 实际代码：AXI驱动补AR/AW/W背压VALID及payload稳定检查、失败后停止驱动、held completion不可撤销；按原Commands解码首completion，并区分观测、handshake、ACK覆盖和数值比较。原7合成周期/3非法AR回归及新增11检查通过；未执行Host。
- 安全提取：冻结头文件确认AllowAlloca=false，534原始区间不重扫生成代码；每段检查原栈槽仍caller、helper零alloca及LLVM verifier。2048派生指针/lifetime/内存差分及禁止操作负例通过，仅微测。发行包无CodeExtractor.cpp，不声称冻结实现源码审计。
- 实际Host转换：原47675在90秒完成459/534后超时，无最终对象；保留失败。基于持续进展一次150秒预算原54673在124.264秒完成534段，IR SHA d61f65e37cac1038a476d0038cae0c3ebe1ed4878c7a4ff6e1ab082eef3aebd6。
- 静态审计：106 strict、17sink/26source调用顺序及ABI保持；helper零alloca。最大eval块82599行降至20455，但eval增至578176行、helpers731378行，文本IR约1.8GB，代价异常；未提交机器编译/Host运行，不能冒等价或数值PASS。
- 五块128：完整原Chisel仍0/5，固定4096。Qwen2首RMS输入/捕获准备；0.8B L0/L3只读真实输入可用，各自输出捕获仍待接；35B两层缺完整权重及原准入资格。L0 strict下溢FAIL和MoE同分待定契约不变。
- 完整RTL数值与完整block MAC利用率未测。临时清单已核，清理0；唯一证据/依赖保留。
- 下一步：先解释提取后packing/文本体积及剩余大块，选择成本可控且重新资格的编译变换，不重复已超时llc或危险split。
- 终态：8352成本解析与21139有界流式统计均exit0。总指令460651→1322221；caller分配类型83537→1753342字节（非实际机器栈帧）。1.92GB文本中503003条GEP占1.875GB，匿名aggregate类型重复打印为主因，但真实packing指令也近三倍。不交llc；named struct仅减文本不能宣称解决。
