# 实际 bank / owner 源码与 N160 主机模型数值证据

[SUMMARY.json](SUMMARY.json)保留源码、输入、编译及输出身份，不包含权重、张量、
二进制或生成IR内容。可复现源码与范围见
[候选说明](../../../candidates/qwen2_resident_matrix/transposed_owner/README.md)。

前端门：48项控制/结构测试；实际owner＋service编译/12份CHIRRTL；81份冻结
生产/HF源码的Scala类型检查。默认关闭single/burst两档严格IR相同。第一次门
因三条assert来源字符串不同失败，保留原FAIL/diff，修正同文件名/源行后才通过。

数值门：使用已封存M128归一化输入和Wq前160输出通道，model实际bank读出的
7680次accepted step驱动host逐K FMA；同一model从物理返回tile写回81920B，
640次ACK后得到20480值，全部bit等于独立原始输入点积。再在ACK输出上单独
加原bias，匹配已封存qr前160列；没有将golden注入返回路径。该次耗时1.31秒
包含小host库编译，属于派生N160单位组，不是完整Q投影或全block。

56,196是软件协议ticks，Matrix实际时延/硬件吞吐未建模；本次没有RTL或端点
FPU执行。整个kernel只typecheck，未展开，Host完整命令链仍未验。
CI只运行48项控制/结构测试和真实前端/typecheck，不下载实际权重，也不执行
这个真实输入C++数值门。新提交的CI要另行核验，不能继承本地PASS。

现有M128 native/FP32-final FAIL与数值政策待决定保持；down prefix seed、
FFN融合、完整Host、carried/更长prefill及最终硬件门仍开放。
