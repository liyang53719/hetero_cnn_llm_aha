# 03:33 依赖与真实参考输入闭包恢复

实际从官方Maven正常证书验证下载26个缺失jar，共19812656B，全部精确SHA/长度匹配；15222 exit0/127.86秒。复核857核心class后仅增量编译此前缺依赖的Diagnose入口，75467 exit0/6.98秒新增3class，未重复全核心编译、未Host elaboration/执行。原Commands精确版本及后续替代的远端来源仍待核，最新执行闭包未恢复。

Qwen2十三真实FP32输入重验一致，不重复生成。两个允许历史源码包恢复五个原算术/trig源文件，与既有精确pin一致；原Host-double trig重新编译执行，1024×64容量的cos/sin各262144B匹配原pin。此容量不是用户长序列档决定。六负例（非finite/除零/underflow/负sqrt/预算/形状）和两小Dense对照通过；未执行真实RMS/Q或完整21-op，不继承丢失全参考PASS。

0.8B原桥24参数段重验，补L0冷history49152B/state1048576B全零，L3 trig16384B匹配原capture pin，并验证污染/截断拒绝。使用overlay引用原桥，不复制权重；两层逻辑只读仅缺hidden，L0显式dt_bias padding适配仍缺。无伪造hidden，35B完整payload及访问限制仍未解，不重试下载。

五块M128完整原Chisel仍0/5，最终RTL及完整block4096有效MAC80/90%未测。原head4 underflow FAIL与顶层预期8 FAIL保留，未知旧Host不重启，丢失PASS不继承。下一步沿恢复的真实输入/算术执行有界参考重测，并核Commands来源，不把依赖/类型/小例PASS冒完整数值。

开工main7be8a41012de15e19185460801f19b7274eb9703；工作树干净，临时清单检查，既有数据清理0。资源约9.1GiB/57GiB。各本轮session已终态，无完整profile新启动。只发布允许摘要/hash，不上传源、权重或生成数据。
