# 独立 GDN32 完整模型执行候选

这是原 same-job 模型主线的独立版本，不是叶子测试、旧159资格或最终RTL验收。旧目录及旧 SOURCE_PINS 不在本发布改动范围。

实际链路：prepare_and_run → controller/flow → 独立 model162 producer → 原结构/端口检查 → selected runtime、原官方权重与 reference → numeric_tail → connect_owned → consumer_owned → 原完整逐字节比较及独立清理证据重验。

硬件仍为同一162源、4096 MAC、一个32-lane Bank和122外部typed ports。五个 M128 profile的构造、容量及接口不依选择变化。不同profile可以独立job从源码重新构建，在同job内完成生成、C++构建及执行；不上传DUT、SV、JAR、缓存或二进制。跨五job只有全部完整数值证据通过且实际生成SV SHA完全一致，才允许合并五块结论；不声称跨链接job的binary相同。

采用独立 literal-diagnostic driver身份。唯一签名改动不影响已审数据/时序逻辑，但尚无新C++运行或性能提升证据。保留O1、single CPU affinity与threads1。

资源：初始MemAvailable至少13GiB，磁盘至少20,671,240,864 B；阶段原资源门与supervisor持续监控不降低。初始8GiB磁盘余量不是持续8GiB保证；普通持续floor为1.5GB，日志等阶段仍保留其更严格原门。每个关键native前输出有限typed资源摘要。P0保留真实AVX512要求，不以AVX2、Scala编译通过或其他profile资格替代。

完整生命周期保留每profile四个host阶段共9000s，加完整DUT watchdog、真实供数、构建、清理和parent预算。五profile同job的四host尾已超过21000s，因此不能启动。单profile保留所有阶段最大cap时也不能默认GO。条件模式仅使用实际已过去时间后的剩余空间，收紧本次build allowance，不减9000s尾、不重置clock、不扩大7200s构建cap。首次安装及20s census另有显式预留，census后再次计算。DUT直接CLI在execute前也重核完整本profile和host尾窗口，迟到不能重入长DUT。

当前仅源码及明确合成的实际reader/入口回放。尚未新Top elaboration、仿真backend构建或五块数值执行，无速度/完整完成时间证据。未提供自动可执行的短诊断冒充FULL，也未激活CI。实际运行仍需独立审定的有限FULL计划、真实fresh host和完整剩余预算全部满足；不满足则拒绝且说明尚未启动阶段。
