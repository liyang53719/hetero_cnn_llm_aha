# Qwen2 resident Matrix：源码候选，生产接线未完成

基线固定为 `43440dbad48c8e8af3112c1ae658db3ae64d76eb`。本目录直接提供原
`BurstProtocol.scala` / `MatrixPipeline.scala` 的窄范围补丁，以及真实 Chisel
seed 控制器源码。没有修改现行生产文件、Host 命令、算术或默认参数。
原 M128 native 数值 FAIL 与待批准的数值政策保持 open。

## 已具备的具体增量

`return_tag.patch` 在原生产模块增加 `returnTagBits: Int = 0`，范围 0..32。
默认 0 时字段完全不存在；启用后 tag 仅随实际接受的合法 step 进入原 8-entry
metadata queue，从返回的队首进入原 2-entry result FIFO，绝不采样当前输入 pins。
这使未来 PV owner 能识别实际返回的 causal-last K 并保留其 signed zero。
现有 endpoint 只回传 context/last，仍不能检测同 context/last 的内部乱序。

`MatrixAccumulatorSeed{Protocol,Controller}.scala` 提供 begin、beat、commit、
ACK 的实际控制状态，读取 raw FP32，逐 beat 写现有 context 的候选接口；没有新
FMA、accumulator、tile payload buffer 或替代数组。两文件目前未实例化。
未来 `enableAccumulatorSeed=false` 的组合分支尚未实现，不能称带 seed 的生产
Matrix 已接通或默认关闭组合已通过等价验证。

## 生命周期和真实地址

- Resident owner 先检查真实 C slot、M/N/K、prefix K、ownerN、已提交 generation
  和 alias，锁住 source slot。服务端只检查 active group、context、选定 slices、
  全局算术 quiescence、beat 顺序/数量和同一身份，不伪装能证明 SRAM 来源。
- 每个 16×32 slice 有 32 个 512-bit beat，完整 16×256 context 为 256 beat。
  第 s 个 slice 的 cluster q、lane j 对应 row=q/2、column=32s+16(q%2)+j。
  未写过的 partial M/N lane 必须由 owner 显式补零，不能读取哨兵作为累加器。
- 所有被选 endpoint 的 32 次写及 commit ACK 全部成功后，且当前 group 仍有效，
  `committed.valid` 才允许服务端把 context 标为 seeded。随后首次 step clear=false，
  沿原 increasing-K 序列继续；普通未 seed 路径 clear=true。
- seeded 必须参与 finish 的闭合检查，不能因它尚未 issue 就提前结束 group。
  所有 Matrix result 继续暂存，最终公开仍等原 group done 成功。
- ACK 一旦 valid，背压期间内容保持稳定。随后发生 abort、身份失效或多余 ACK，
  即使已出示的 ACK 描述 seed transfer 成功，也永久 poison、禁止 committed，
  持续 invalidate 直到 coordinated reset。调用方不能仅凭 ACK.error 发布。
- early/late/duplicate/unselected/wrong-identity/error ACK 均拒绝；缺 beat 或 ACK
  永不发布。失败 lease 不得再改称成功释放；旧 lease 不得读新 generation 的数据。
  Python 控制参考已分别覆盖这些反例；它不是 Chisel 执行器。

生产 BF16 Host 仍要求 N 为 32 的倍数。参考中的 M3/N48 仅测试 padding/地址边界，
不表示生产 admission 已放宽。有限 FP32（含 ±0 和 subnormal）原位搬运；
NaN/Inf 拒绝沿用 resident 数值模型的有限数域。既有 endpoint 未向服务导出 FMA
exception flags 的问题仍 open，不借此修改异常或精度政策。

## 明确记账，尚未绑定周期

启用 T-bit return tag 增加 10T bit 的声明存储，T=16 时为 160 bit；mux、布线和
时序仍未测。Seed 控制器有 138 bit 控制寄存器，owner 还至少需要 512-bit 两读
assembly/skid 以及地址/phase/身份控制。Endpoint valid/reservation、写口 mux、
ICG 和新控制也需要资源，不算免费。

现有 A/C bank 的 word 是 256 bit，一次 512-bit seed beat 需要同一 row bank 的
两次读取。完整 context 是 512 次 source read。已封存 M128 Dense 的恢复流量
81,788,928 B 对应 1,277,952 seed beat、2,555,904 次 256-bit read；另有 prefix
store 流量。这是操作/字节计数，不能直接解释为全局周期，跨 bank 重叠、端口延迟
和 assembly 容量尚未绑定。固定 4096 MAC/拍的全周期分母不变。

## 本门的验证层级

1. 13 个 return-tag 抽象队列测试和 25 个 seed 控制/物理地址测试，以及 runner
   的负面身份检查。没有执行浮点算术或 production Chisel。
2. `scripts/check_matrix_interface_candidate.py` 从固定 Git commit 取真实生产
   source，核 SHA 后在隔离目录应用 patch，使用仓库既有 Maven lock 中的
   Scala 2.13.16 / Chisel 6.7.0 / matching plugin 编译，调用 emitCHIRRTL。
   只抽取原 RetainedMatrix 的精确 BlackBox ABI 和 legacy bundle 声明，未替代算术。
3. 对 original/default0 的 FIFO 与 service CHIRRTL 逐字比较，仅去除 source-location
   注释；检查 enabled width 1/16/32 和非法 width 拒绝；seed 编译检查端口及 FSM，
   不代表生产组合或状态时序仿真通过。

运行命令：

```sh
python -m unittest discover -s candidates/qwen2_resident_matrix -p 'test_*.py' -v
python -m unittest discover -s tests -p test_matrix_interface_candidate.py -v
python scripts/check_matrix_interface_candidate.py --repo . \
  --out work/matrix-interface-frontend --cache work/matrix-interface-jars
```

输出目录必须新建，缓存每次重新核 SHA；日志/CHIRRTL/完整 tool identity 保存到
work 或 CI artifact，不把 jar、权重或 tensor 上传 Git。前端门不调用 firtool、
Verilator，不生成 SystemVerilog，不运行 full block。实际结果以该次 summary 为准。

## 到生产的剩余最小接线

1. `MatrixStreamPort` / `MatrixPipelineService` 增加真实 default-off seed 分支，
   检查 seeded/seen/closed、五个 context、group poison 和完整 finish 条件。
2. Retained endpoint 显式导出 arithmetic busy，接 begin/beat/commit/ACK 和持续
   invalidate；seed/invalidate 时 ICG 必须打开。ACK 必须是 commit 后注册回执。
3. 原 front/scheduler/cluster/lane 的五个 FP32 bank 增加仅 quiescent 可用的
   写口 mux 和 valid/reservation 控制，不能增加第六 bank 或绕过原 FMA。
4. Resident owner 绑定真实 bank ports 和 prefix store ACK，完成 bounded assembly、
   generation/alias/partial-padding，以及 reset 后不消费 stale response 的恢复。
5. 上述组合完成模型/源检查后，才安排小真实硬件接口门；完整 RTL 数值和 native
   验收仍是后续独立门。当前 M16/M128 软件驻留 replay 的全 15 节点 bit exact
   不替代这些门，也不关闭原官方误差失败。
