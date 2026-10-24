# GDN chunk 私有状态搬运控制，独立候选

本批新增真实 Chisel `GdnChunkStateTransferOwner`，只控制一个 head 的 64 KiB 私有状态搬运：cold 零填 initial，warm 从 stateIn 拷入 initial，或在绑定的末 chunk phase16/17 receipts 后从 next_state 拷出 stateOut。固定 64 B 拍、单 outstanding，读成功锁存位模式，写成功 ACK 才推进 beat 和 writeBytes。模块不包含浮点运算、Matrix/Vector/Scalar/DMA/SRAM 实例，不接 Host，不开放已有公共/recurrent M1 拒门。

## 真正实现与尚未证明的边界

- 新 Scala 实现 request/response/held-terminal FSM、完整五 span 与两种规模地址计算、cold/warm generation/root 检查、末 chunk receipt 绑定、失败锁定。四源未来编译闭包为原 Protocol.scala、已封 GdnChunkProtocol.scala、已封 GdnChunkAddressPlan.scala 和新 owner；Chisel/Scala 工具依赖尚未为本批授予编译资格。
- 原 MemoryResponse 没有 nbytes。本批只能检查真实 tag/error；固定完整拍由请求对齐、满 mask 和既有 transport 合同约束，不能声称独立响应长度验证。写请求和 done 在背压下保持，未接受的请求不产生 outstanding；响应只在 wait 状态接受。
- 错 tag 优先于 error；任何失败不计该失败拍、localDrained=false，失败 terminal 消费后锁定。失败可能留下部分私有写入，不回滚、不发布。恢复须连同 transport 排空/复位，不支持仅复位 owner 后复用可能遗留的响应。成功再入仍依赖既有唯一响应/no-stale 合同，不是防重放机制。
- `transferComplete` 只表示本命令 1024 个写 ACK 完成，`localDrained` 只在成功时声明本 owner 无 outstanding。结果没有新 root、generationAdvanced、stateCommitted 等发布权限；原 Host 双根/final-residual fence 未改。
- receipts 是未来可信 scheduler 输入，字段核对不是来源证明；本批没有算术生产者或共享 root 锁。scheduler 必须保持本命令期间来源状态与根稳定。冻结 ChunkProtocol 的历史注释描述原 types-only 批次，不代表本新 owner 已有顶层生产接线。
- M16/M128 仅沿既有 chunk64 私有布局分配状态，绝不是把 recurrent M1 循环冒充完整 prefill。位拷贝保持 NaN/符号位，不是 FP32 算术或 GDN 数值验证。

## 小控制测试与资源边界

`transfer_model.py` 为对应 FSM 的纯 Python 合同模型；`tests.py` 直接核源码固定字节/literals，并枚举 M16/M128 的指定 head/路径、地址、请求/响应独立 fire、背压、错误及终态。测试不是 Chisel 执行、真实 AXI/iDMA/ACK 或 RTL 仿真，不产生模型算术输出。

建议唯一测试命令（目录变量由 root 绑定到已核精确路径）：

```
/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python -I -S -B tests.py --base BASE --contract CONTRACT
```

仅提案：10 秒总墙钟、单 CPU、256 MiB 地址空间/内存限制，stdout/stderr 各不超过 1 MiB，全部产物新 `/tmp` 输出目录。执行须在本批源码与测试独审后由 root 单次准入；本文件冻结时未执行本批测试、Scala 编译、elaboration、RTL 或真实模型。INPUT_PINS 的 11 项是小源见证，不是完整工具链闭包。当前 Qwen2 full 的 UNKNOWN 状态不变，不读取或触碰其候选/活动流。
