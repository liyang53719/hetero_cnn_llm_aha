# 实际 M4/M8/M16 bank-backed Attention 校准

中文状态：已完成一次修正M4、一次M8、一次真正M16多行job数值验证与安全receipt保存；独立证据审查和2项普通/优化模式原文件校验均已通过；M128、输入/输出物理放置与RTL仍待做。

四份原始安全JSON逐字嵌入EVIDENCE.json，各自SHA固定。首次M4失败保留，原oracle已完成，candidate被错误观察器的逐key score邻接假设中断。相同M4回归复现具体异常，修正只将packed candidate改为全操作hash观察；原oracle的严格score抽取和全部score/output比较保留。首次失败未保存完整source map，明确标记；三个成功receipt包含同一d2508047…fef5d5源闭包和Python interpreter身份。

实际结果（Python模型、合成有限输入、Fraction算术）：

- M4：reference0.606454s，candidate0.517928s，总receipt1.140584s，CPU1.136228s，peakRSS58812KiB；原1920请求、packed404steps、840scratch事务。
- M8：reference2.040921s，candidate1.653622s，总receipt3.715129s，CPU3.714959s，peakRSS64768KiB；原6912请求、packed840steps、3024scratch事务。
- M16：reference7.885280s，candidate5.632890s，总receipt13.550187s，CPU13.543965s，peakRSS66588KiB；原26112请求、packed1808steps、11424scratch事务/34274服务edge。全部24576output和1632score与原owner逐bit相等，ACK/return数量平衡。

每次都内部25秒/外部30秒约束，M16是一份m16 job，不是16次m1。CLI总时间还包含源门/写summary等开销，分别约1.305/3.883/13.716s；receipt时间不等同硬件周期。

固定4096MAC、全块6014828544 useful MAC和SiLU成本不变。当前7P scratch串行服务账本本身就不能支持80%整块利用率；没有RTL、fullblock或80/90% PASS。Q/K/V输入及最终输出仍在host fixture/观察存储，真实scratch路由、selector和staging lease还需接线。

普通证据测试：`python3 -S -B -m unittest candidates.qwen2_resident_matrix.attention_bank_multirow_evidence.test_evidence -q`，同命令加`-O`。独立复核原文件时设置`BANK_CALIBRATION_RECEIPTS`到包含四份JSON的目录；未设置时只验证仓库内固定原始字节和完整账本，不声称重新读取外部原文件。
