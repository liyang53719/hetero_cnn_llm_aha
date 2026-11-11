# 23:33 固定4096候选Host完整elaboration与输入边界修复候选

## DONE精确范围
2233五源overlay与其余860已验class身份重核后，实际生成完整候选Host CHIRRTL/HWIR，原session45888 exit0：emitter3.71秒、CHIRRTL14.12秒、HWIR56.93秒。保持同LegacyV0固定4096配置，没有按profile重新配置。新HWIR SHA6ef3403c3dfa5a0d1ceaec78e2f02f4556edff3f241b8d53b5b28f719c4673d0。
两路静态审计确认85公共Top端口方向/名称/宽度逐项一致；8Matrix+8ICG+1iDMA实例及extern声明、可达拓扑一致；105条error文本multiset、105fatal、额外1 immediate assert保留。3条内部诊断wire确实有inner symbol，新增寄存器恰8+3bit。第一次检查器误找sv.wire，实际为hw.wire，原INCOMPLETE证据保留，纠正检查器后通过。
这是完整Host生成与静态诊断保留，不是新Arc机器码/运行时可见性、控制谓词等价或完整数值PASS；没有放宽错误优先级、改变精度或公共ABI。原共享源和可执行Host未替换，局部诊断mask非完整根因。

输入并行完成244处真实源/桥字节边界比较，包括转置末端、31/32列、AB列15/16分界，全匹配，未重复巨大矩阵hash。发现L0 dt_bias有效文件32B但原allocator预留64B：已核真实RawPrep readParam请求64B、只消费低16 BF16；非Dense iDMA发单64B beat。原allocator没有定义尾32B字节。
实际实现独立只读映射候选：保留原32B源与hash，尾部显式零32B，完整64B读；7项测试覆盖坏hash/越界/跨张量/写拒绝、有效16BF16不受三组高半数据影响。映射SHA80ec6c294f30499079744a58af3307e8829080c096a1795fd08540339dcf7777。此为新padding策略，不冒原未知padding恢复；尚未接入Host或执行原profile。

## 五块128 / ONGOING / TODO
完整原Chisel数值仍0/5，最终同刺激RTL未通过，4096完整block有效MAC80/90%未实测。Qwen2真实FP32输入/独立21-op参考闭包仍在；未知旧Qwen2/L3任务终态及启动边界待定，不重启。0.8B L0/L3仍缺原hidden及L3旧身份证据，新增源码无生成者。35B L0/L3完整payload仍缺，未重试受限下载。原head4 underflow FAIL及RMS顶层预期8的FAIL保留，不继承遗失PASS。
下一步将新HWIR带严格断言/17native接入已验证编译IR路线，核实际state/layout诊断可读性并做有限边界对照，不以无限局部资格替代完整prefill。padding映射仅在明确新输入身份下接桥，不修改权重有效数据。

## 版本、CI、资源与清理
开工main d23a733c7b4a57e41a30945877ac48ac7b77781b，CI43113559240成功，仅payload guard非数值。工作树干净，约9.1GiB可用RAM/56GiB磁盘。临时清单已核，既有数据清理0，唯一证据保留。45888已终态，无本轮新完整profile运行。发布仅允许摘要/hash，不包含源码、原始日志、权重或生成数据。
