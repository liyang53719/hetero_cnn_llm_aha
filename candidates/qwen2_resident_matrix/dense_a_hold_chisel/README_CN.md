# Dense A-hold：实际 Chisel 默认关闭接线

本目录把已审查的 `dense_a_hold_candidate` 控制方案接入实际组合后的 `TransposedDenseDownOwner` 和 `TransposedDownDenseBanks`。`enableAHold=false` 为默认值，现有调用者和外部 `DenseOwnerIO` 不变。补丁只修改这两个文件，不修改冻结的 Python/native 数值证据、Public 运行源码、W 布局或 DMA 描述符。

当前已完成源文件组合与冷控制参考检查。Scala 编译、CHIRRTL elaboration、硬件握手模拟尚未执行；本地仅有 Java，没有现成 sbt/scalac/Chisel jars。准备源文件并不生成 RTL。专用 frontend CI 只负责源文件编译和四种 CHIRRTL 结构检查，CI 通过后仍不能宣称硬件握手、数值或时序验收完成。

## 接线与容量

- 关闭时仍用 Queue4；开启时用 Queue3 和一个 `128×BF16=256 B` 的 A hold。context0 发出 A+B 同步读取；同 K 的后续 context 只读原 B banks。
- 信用条件始终包含 `Queue.count + banks.response.valid < depth`。待返回 RAM 数据占一个信用；每个 Queue packet 在响应沿复制完整 A 数据，不能引用可变的共享 hold。
- context0 响应可在同一沿捕获 hold 并接受 context1 的 B-only 请求。下一沿才消费 context1 的 B 响应。最后 context 的响应完成私人 packet 捕获后才清除 hold；单 context 的捕获和释放在同一沿完成。
- 复用现有不允许回绕的 `groupSequence`。新增 hold-generation 32 bit、pending-generation 32 bit、ordinal K 12 bit、valid 1 bit，以及 bank selected.readActivation 1 bit，共 78 control bits。K-window 的 pair permutation 仅改变实际 SRAM 地址；所有 context 仍按原 ordinal 顺序发给 Matrix。
- 有效 operand payload 从 `4×320=1280 B` 变成 `3×320+256=1216 B`。完整源声明 FIFO packet 为 4359 bit：开启后 FIFO+hold payload 为 `3×4359+2048=15125 bit`，另计 78 control bits。常量 lane 消除、FIFO 实现、寄存器保留和物理面积仍需综合确认；这不是物理面积测量。

A/B 仍各 16 个既有 SyncReadMem，A 深度 1376、B 深度 160，每 bank 一个读调用和一个写调用。新增 readActivation 只屏蔽 Dense gather 的 A read-enable。activation RMW、tile read/RMW、raw-KV 分支保留原路由和排他检查。B-only 仍受原 read.ready、tile busy/lease、raw lease 限制；此步没有让 FFN tile 与 Dense 同时使用 A port，也没有新增 A port。

## 失效与既有债务

非 execute 状态、未提交 A、既有 resetRequired、输入 clear/load、window.invalidateLease、DMA 坏返回和 hold identity 错误均禁止新 gather，并清除 hold。setup、N group、window、chunk 的状态转换因此不能延续旧 hold。正在执行时 invalidateLease 进入原 Protocol fault/drain，不能在同一 group 中重新读取已变化的 A。

DMA 错误使用 `valid && outstanding && responseBad` 的 offered-response 条件，不依赖 `burstResponse.fire/ready`，避免 `read.valid → activation.ready → burstResponse.ready → read.valid` 组合环。坏返回同沿禁止新 bank 请求及 Matrix packet 发布。已接受的 RAM 返回在到达沿丢弃，队列在已登记 fault 后排空；DMA、seed、Matrix done、写数据/ACK、tile RMW 等既有债务继续由原 FSM 退休。补丁不清除这些 outstanding 寄存器。

这没有增加新的本地 reset API。真实硬件 reset 仍属于既有协调 reset 域；冻结模型的 local_reset 测试不能冒充此补丁新增了 reset 端口。

## 测试边界

`test_source.py` 检查 13 个真实源单元可重复组合、只修改两个目标、默认关闭 ABI、同步信用、资源声明、失效路径和 K-window ordinal/address 映射。部分测试重新执行已冻结 Python 控制参考：M16/K32/N160 完整 packet 对比，以及 M16/K256/N160 的同沿坏 DMA 返回/债务退休。这些不是 patched Chisel 的执行结果。

`test_frontend.py` 使用合成 CHIRRTL 测试审计器的正/负例，验证非法 bank port、FIFO 深度、hold 形状、额外寄存器/存储均失败；runner 测试使用 mock，不能产生编译成功证据。

`AHoldUnit.scala` 是待运行的实际 owner 观察 harness。两个开关配置分别覆盖 M16/K32/N160 packet、长背压、Queue 信用及主动 lease fault 后退休；开启配置另覆盖 M16/K256/N160、splitK256 的同沿坏 DMA 返回。它不实例化 Matrix 算术，正常 packet 观察完成后故意终止并检查 drain，不能称为成功完成业务 block。此文件需要 chiseltest/ScalaTest，专用 frontend CI 不编译或执行它。

## 独立 frontend CI

`.github/workflows/qwen2-dense-a-hold-frontend.yml` 仅自身 YAML 的 main push 和手动入口触发。launch revision 更新用于显式发起下一次资格检查；现有通用 frontend 覆盖不变。当前这份文件还没有发布或启动。

`check_frontend.py` 复用现有 Maven lock：SHA-256 `e15bbf22b74552ed6a4fc61a7137564c2543488d928cbdff77f27af2dfd3204b`，与 `scripts/check_matrix_interface_candidate.py` 相同的 87 个 pinned jars、Scala 2.13.16、Chisel/plugin 6.7.0；只从现有 Maven Central origin 获取并逐项验 hash。不解析新的 chiseltest 依赖。

编译输入为 13 个组合单元及 `AHoldElaborate.scala`。一次 JVM 产生 enableAHold off/on × minimal/full optional ports 共四份 CHIRRTL。每份检查 32 个 1R1W banks、一个 depth4/depth3 的原 packet Queue、2048-bit hold 和 78-bit control 增量；off/on 对照要求其他 owner/bank 寄存器不变。完整模块只允许真实 owner、banks 和 Queue，无 Matrix/HardFloat 黑盒或算术单元。

编译前和返回 PASS 前，重新核对全部已记录仓库输入、13 个生成源文件及其精确文件集合、emitter、source pins、workflow 和每个 jar。运行中任何持久漂移都会保留 FAILED 证据；mock 测试包含 source、额外 emitter 和 jar 变化，不能把 mock 的 PASS 当成真实 frontend 通过。

预算：单 JVM 1 GiB heap、1 个 active processor；依赖下载最多 4 workers/120 s，编译 180 s，四配置 elaboration 合计 90 s；总 runner 420 s，保留 kill-group cleanup 时间；CI job 9 min。禁止 firtool、SystemVerilog、Verilator、C++ 和全 block 执行。仅上传 summary、源 hash、依赖 hash、最多 4 KiB 的清理后诊断，不上传 jar、class、CHIRRTL 原文、日志全文、输入或权重。

执行边界明确记录：CHIRRTL 生成会设置 `chirrtl_generated=true`，`rtl_generated` 始终 false；硬件协议、算术和业务 block 验收始终 false。接下来的硬件握手资格检查需另行安排预算。
