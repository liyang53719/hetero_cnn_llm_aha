# 原 M128 归档 operand 内容/索引离线层

见 [安全源码与范围](../candidates/qwen2_full128_packet_semantics/README.md)。一次只读归档pass验证847,872 accepted operands的预期因果/GQA6/tail内容与SHA；独立actual664项复核没有重解析原流。不是DUT/native/reference/RTL重跑，不证明DDR握手或完整result tile数值。原完整M128软件观测域PASS、全部旧FAIL和canonical任务状态保持；full29/noninterference/90%硬件利用率不升级，无未执行Chisel候选。
