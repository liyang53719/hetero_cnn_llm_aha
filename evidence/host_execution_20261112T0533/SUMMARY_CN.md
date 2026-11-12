# 05:33 真实RMS参考与输入桥恢复，依赖下载阻塞

实际重新执行真实Qwen2 M128×1536 RMS独立Fraction参考，54965 exit0/5.563秒/786944预算操作；x/gamma FP32源hash通过，norm0 SHA ccf1e6c065c6bc4e90458194aeda7475149451ac73479a6781d2fd638bf631df。shape/预算耗尽/scalar下溢三反例拒绝。只恢复本步必需输入，未重复全13权重；仅RMS参考PASS，不是Q/全21/Chisel/RTL。

0.8B重建可复现L0 15段（真实参数+冷history/state）、L3 12段（含原pin trig）及完整锁定hash。dt_bias原32B不变，明确新zero-padding映射64B。四项适配/污染/损坏/越界/只读拒绝测试通过；完整准入仍拒缺hidden，L3原hidden身份待核。未Host或35B下载。

历史155源逐pin通过；26缺Maven依赖成功恢复7项8834221B。第8项json4s-native-core官方URL20秒超时，原68476 exit1；复用成功7项同URL一次有界续取2971仍超时，无新增，已停止，余19项。不是策略拒绝，未换源；保留两次日志和可复现恢复脚本，未进入完整155类型检查。

五块M128完整原Chisel仍0/5，最终同刺激RTL及4096完整block有效MAC80/90%未测。原head4及顶层预期8 FAIL保留；未知旧Host不重启，丢失PASS不继承。下一步补缺依赖及真实hidden/执行闭包，独立参考后续沿明确身份续进，不把小步PASS冒全链完成。

开工main4f87ff2f526092bc64a477cca14aae3b671f56be，工作树干净，约9.1GiB/57GiB。临时清单已核，既有数据清理0，各新session终态。仅发布允许摘要/hash，不上传源码、权重、原始日志或生成数据。
