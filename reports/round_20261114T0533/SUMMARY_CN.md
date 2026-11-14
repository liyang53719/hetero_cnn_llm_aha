# 2026-11-14 05:33 hetero：INCOMPLETE

统一4096 Matrix MAC及原数值策略不变。五块M128完整原Chisel仍0/5，完整RTL和完整block有效MAC利用率未测。

## 真实持续执行/恢复修复
修正periodic候选保存后accept_new=false而恢复默认true造成后续背压刺激不一致的问题；在两端显式统一刺激，再实测周期安全保存。
原session95163 exit0，从已验11831无reset/relaunch续8849周期至20680，实际新增95个读取beat、DUT active72.996秒。每约1000周期停止新AR后排空，共9个完整安全包；90秒墙钟提前收尾，未触发110秒硬界。最终包SHA404f47f8a7186b95d46b9d781a5e7ce821c566e247ff02a1b6992ea0d53a56cd。
最终完整包fresh-process再120周期至20800，轨迹及20块终态hash一致，真实ACK仍6144B/首行、参考0差异，第二行未写回。前8包仅完整hash核验，不能称逐包恢复已测。最新可恢复状态为20680，20800仅比较终态。没有重算前缀或重启旧29364。

## Chunk严格故障连接到真实局部硬件
原Vector Bank经Chisel发射RTL/Verilator，4例通过。lane12实际返回已定位故障0x801c6a52、flags3、flagsValid1、error1；精确subnormal无错、tiny舍零报错、正常乘法无错。每例7周期返回背压保持，其余31lane不受影响。只是原Bank数值拒绝/保持资格，不是完整Chunk phase6/Host执行，不代表新32-lane每周期发射架构已实现或五块通过。L0当前数值FAIL和历史strict head4 FAIL仍保留。

## 真实adapter边界测试
直接原UnifiedMoeSharedArithmeticAdapterV5小模块RTL测试71例通过：64种flags/valid组合逐bit保持及4周期背压；完整64-bit txn、serial/policy错误、缺physical-issued、issued跳2、缺allocation被隔离/拒绝，error payload和poison保留，正常retire释放。
lease及Core计数/响应是合成测试peer，因此不能冒真实allocator→Core共同执行；也不能把本轮与上轮Scalar分层资格拼成完整MoE通过。初次小probe因circt命名遮蔽编译失败，改_root_.circt后编译通过，原日志保留；未改生产数值策略或安装门。

## 维护及阻塞
基线main6f73da4a24649790cae65e41c772d3ebffb6825d，CI43557468380 success仅payload守卫。旧29364仍Unknown不重启；35B真实权重、冻结Torch运行闭包、MoE数值/tie资格仍缺。工作树clean，临时清单已核，清理0；保留源码/唯一证据/运行文件，仅提交允许摘要与中文计划。
