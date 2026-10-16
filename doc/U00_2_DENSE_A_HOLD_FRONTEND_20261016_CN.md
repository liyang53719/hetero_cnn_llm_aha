# U00.2：默认关闭 A-hold 的实际 Chisel frontend 资格检查

2026-10-16，原始 CI run [38973350757](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/38973350757) attempt 1 在 main commit `3ada1a4de83cfaf9062fbfa8c13604c68e8fff32` 成功。实际编译 13 个既有 owner/bank/协议源单元及一个 emitter，随后生成四种 CHIRRTL：A-hold off/on × minimal/full optional ports。

实际编译 15.713 s、四配置 elaboration 4.776 s、依赖获取 1.268 s；整个 runner 24.819 s，处于 420 s、1 CPU、1 GiB heap 的批准预算内。没有运行硬件握手、Matrix 算术、完整业务 block 或时序分析。

## 已验证的资源声明

每份 CHIRRTL 均只有真实 `TransposedDenseDownOwner`、`TransposedDownDenseBanks` 和一个 operand Queue。A/B 各 16 个既有 SRAM bank，A depth1376、B depth160、width256，每 bank 一个读端口和一个写端口。没有新增 SRAM、Matrix 或 HardFloat 单元。

关闭时为 Queue4、无 hold；开启时为 Queue3 加 `128×BF16=2048 bit` hold 和 78 bit 控制增量。其他 owner/bank 寄存器与 FIFO 控制形状一致。有效 operand payload 从 1280 B 变为 1216 B；完整声明 FIFO+hold payload 从 17436 bit 变为 15125 bit，另计控制增量。这里是 frontend 声明计数，不是综合后的面积或寄存器保留结论。

A-only gather suppression 已接入实际读使能；B 路由、每个 Queue packet 的私人 A 副本、pending-response 信用和原有排他 lease 保留。当前仍未实现 Dense 与 FFN tile 共享释放出的 A-bank 服务时隙，不能把 bank read 数量减少直接计入 80%/90% 利用率验收。

## 原始证据与完整性

只归档 artifact `12076709705` 的三个原始小文件，位于 `candidates/qwen2_resident_matrix/dense_a_hold_frontend_results/`：`summary.json`、`source-sha256.json`、`dependency-sha256.json`。它们保持字节不变；不提交约 42 MiB 的四份 CHIRRTL、日志全文、jars、classes、输入或权重。

ZIP 10,606 B，SHA-256 `513bb551c9b1b6943188c3cf7a9672d8e9550fe8381466ecffaf2eb3f3f011cd` 与 GitHub artifact 元数据及 job log 一致。63 项仓库输入、14 项生成/编译输入、87 项锁定依赖逐项核对；编译前及返回 PASS 前的 hash 相等。独立审查复核了源组合、依赖和四份声明结果。

归档验证器拒绝 run/commit/artifact 身份变更、原始文件任意改动、重复 JSON key、额外 JSON、配置缺失、端口/Queue/hold/寄存器变化及超出证据范围的验收声明。它验证既有记录，不再次启动编译或 EDA。

## 本节点 checklist

- [x] 默认关闭的实际 Chisel A-hold/Queue3 接线及独立源审查
- [x] 32+32 项冷源文件、参考控制与 mocked runner 检查
- [x] 原始 CI attempt1 实际 Scala 编译
- [x] 四配置 CHIRRTL elaboration 与 32-bank/1R1W/hold 寄存器声明检查
- [x] 安全小证据归档与 26+26 项身份/范围负例验证；原始 receipt 已独立复核
- [ ] 实际 owner 硬件握手：长背压、同步返回、同沿坏 DMA、lease/abort 和全部债务退休
- [ ] A-bank 时隙仲裁与 FFN tile 合法重叠
- [ ] W 连续布局/描述符带宽与结果槽联合调度
- [ ] 完整业务 block 数值、实际 RTL wall-cycle MAC≥90% 和综合后资源/时序

中央 `doc/block_checklist.yaml` 的 U00.2 可增加“默认关闭 A-hold frontend 四配置通过（上述 run/commit）”这一子项；U00、完整 block、RTL 协议、数值和利用率状态保持未完成。下一步先审查小范围硬件握手路线与预算，再考虑执行。
