# 2026-11-10 10:33 主线推进

## done（精确范围）
- Qwen2真实M128七Dense：5,989,466,112逐K FMA及2,949,120输出的数学参考位值/flags审计；有限BF16乘数+FP32累加器，RNE/gradual前提。实际flags0/1。输入BF16转换、QK/PV/SFU不在范围，不称全block通过。
- 0.8B L3真实M128：1536对sqrt/div及四norm全1,771,008 mul/712,704 add精确链复核，全部BF16保存输出一致。仅四阶段数学参考资格。
- 0.8B L0：冻结Conv/AB边界后10,711精确节点复现head0/3/11/13 tiny-inexact；原fatal保留，完整block INCOMPLETE。旧head4硬件FAIL是不同身份，未覆盖撤销。
- 官方pin源码的chunk64/prefill分支复核；项目cold M128限制不能归因官方整体。

## ongoing
- 原Chisel Host解释链需要原真实SV BlackBox：8 Matrix+8 ICG+1 iDMA；SFU仍原Chisel IR，不用软件oracle替硬件。
- 当前Top关闭seed是原显式参数决定，历史seeded native库不能混用。建立当前22端口unseeded transport适配与核验，不改RTL/4096/容量。
- 原C++库编译复用已生成对象，单线程/600s/5GiB，不重elaboration，不提前长RTL数值回放。原session58224已在600.002s预算到期，exit-9/timeout=true，保留对象，不是数值FAIL，未重复启动。

## todo / blocked
- Qwen2剩余标量/格式转换/attention异常契约与完整原Chisel执行。
- L3其余阶段精确资格、原Chisel完整执行。
- L0不可绕过fatal失败继续补假的FFN最终输出；先完善上游真实资格与归因。
- 35B L0/L3官方CDN策略阻塞，无重复下载或绕路。

五块完整M128原Chisel/同RTL仍0/5；不存在新的完整硬件PASS。利用率没有完整block RTL实测，80%/90%目标不改。所有生成输入/参考/权重留本地，只发布源码/pin/hash/摘要。临时文件仅盘点，没有清理运行、被引用或唯一证据。
