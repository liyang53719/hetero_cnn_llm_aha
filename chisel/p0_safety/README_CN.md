# P0 安全修复：以 Chisel 为设计源

基线：02549039beda0c1c42b8375ace2dca1c0d8cd9e2。

本目录迁移四个自研硬件模块：group8 控制、Matrix tile payload、transpose、Shared-L2 fabric。为去掉旧 Norm loader 对手写参数化 transpose 的实例依赖，同时迁移 Norm loader。没有修改原 RTL，也没有把修改后的 RTL 包进 BlackBox。

实际硬件逻辑位于 Scala/Chisel：状态机、地址检查、计数器、mask/FP32-BF16 打包、寄存器、同步 SRAM、仲裁。仅 `RetainedDescriptor` 和 `RetainedMatrix` 是未改动的现有依赖；它们不是新的算子实现，完整集成数值还需原实际 leaf。

## 执行

```sh
cd chisel/p0_safety
export MAKEFLAGS=VM_PARALLEL_BUILDS=0
sbt -batch compile Test/compile test
sbt -batch 'runMain heteronpu.p0.EmitP0Safety generated'
python3 scripts/check_emission.py generated
python3 scripts/verify_emitted_abi.py generated
```

MAKEFLAGS 采用 Verilator 支持的单编译单元方式，避开 chiseltest6 预包含头与 Verilator5.020 的 PCH 冲突；不会关闭硬件断言。Emitter 对公开 root 的 scalar 端口添加 Chisel dontTouch 注解，避免常量输出被跨模块优化删除；不修改生成 SV，不禁用数据通路优化。

测试强制使用 ChiselTest + Verilator，非 Python 模型替代。Matrix payload 测试由外部端口提供 accumulator fixture，仅验证喂数与写回，不宣称测试了 MAC 算术。Group8 测试在真实 Chisel 调度器的子模块边界注入响应，仅验证协议、状态与错误；不是 pinned-iDMA 整网数值。

## ABI 与集成

公开 root 名与旧模块名相同，scalar 端口保留；新增 group8 `reset_required_o` 和 fabric `address_error_o[2:0]`。Chisel 参数在 elaboration 时固定，生成模块不是接受 `#(.ADDR_W(...))` 的参数化 SV。不能直接混编新旧同名模块或沿用旧参数覆盖；集成 TB 的实例需使用所选 elaboration 配置。所有默认 root 配置为 ADDR_W=15、16 bank、每 bank 6144x128，实际容量 1.5 MiB，不是编码上限 2 MiB。

`Group8Integration` 内部已迁移 Norm loader 与 payload。编译其生成文件时保留原 descriptor 与 Matrix endpoint 及其算术依赖，排除旧 group8/payload/transpose/fabric/Norm loader。新的 `P0AllRoots` 仅用于一次性生成去重模块，不是芯片顶层。

Fabric 使用 SyncReadMem，不假设上电为零。非法请求不 grant、不触碰 SRAM，并锁存诊断；旧 ABI 无错误 response，集成 supervisor 必须监控诊断，进行中止/超时/复位。这不等于完整 SoC 错误恢复已实现。

Group8 DMA 错误锁存 status=3，错误完成一次后进入 reset-required 状态，拒绝新请求直到 reset。Matrix command 只在 descriptor 合法之后发出并保持到 ready。正常 completion 仍晚于最后一次输出 DMA 响应。若底层永不响应仍需系统 watchdog，不伪造完成。

## 验收边界

所有生成 SV 应从 Chisel 重新生成，禁止手改。保留旧 checkpoint，不对原运行目录覆盖构建。任何设计变更使用新 chain_id / build_id；不能从旧 checkpoint 验收新设计。800 MHz/1.250 ns 是约束目标，不是本包的 DC 签核结果。

本包不改变固定 K=1536、16x32 tile 几何，不优化 Matrix issue 吞吐，不声称完整 decoder 或三模型 q1024 已跑通。最终测试结果以实际 CI 日志/JUnit 为准，不根据本文件推断 PASS。
