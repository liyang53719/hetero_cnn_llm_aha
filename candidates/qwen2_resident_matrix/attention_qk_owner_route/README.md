# 原始 owner 的 QK 单 key final-only 路由（默认关闭）

## 当前工作
- 已实现候选：直接修改 Qwen2ContinuousBlock / QwenOwnerKernel 的真实请求、结果与完成连接，零模糊独立补丁。
- 已完成：独立冷控制/源码审查，15+15 测试通过。尚未编译或展开本补丁，未运行数值任务。
- 不属于本片：16-key packing、PV 六头组、raw scratch 路由、panel384B、完整 Public 程序或吞吐声明。

## 实际连接
新增 enablePackedQkSingleKey=false 参数，只允许 pipelined、原始 H1536/12头/2KV头/headDim128、maxTokens<=128、非 Qwen3.5/BF16GDN 借用模式。
core 实例化已审查 PackedAttentionStreamClient；kernel 在原始 mode0 的 packedOwned 期间，把 group/step/result/done/abort 接到同一个 MatrixPipelineService，隔离 legacy 与 Dense 握手。没有新 Matrix 数组、top 或结果 FIFO。
现有 DDR 请求/ACK、local Q 读取、K 地址、输入 BF16 舍入完全不变。每个 key 仍8次深度步进；前7步以实际 operands.fire 推进，最后一步发出后等待 retained FIFO 的 final result。原始 acc16 只在最后结果出现时接收16个对角选中值；原有16次 Add、随后 Mul、score SRAM 写入顺序不变。
这是一条单 key 桥接路径：客户端仍启用8个既有slice，B的16列之后为现有零填充。因此物理 issue 成本比旧单slice单key路径高，不能据此声称优化或16-key吞吐。

## 生命周期 / 错误
- packedOwned 从 start.fire 保持到匹配的客户端 completion.fire；期间核心 finish 不得发布 owner completion，也不能进入下一 key。
- 实际16KiB FIFO head 在 fold/scale/score 写完成前不 ACK。仅复制到原有 acc[16]，没有新整tile缓冲。
- 正常score写入完成后下一拍才允许 result ACK，再等待 matching done 与 completion；现有同步写没有外部ACK。本片没有把score改接raw scratch。
- 选中非有限结果在折叠之前触发原始 Numerical fail；非final返回不再逐拍检查，错误可延迟到final。非有限FMA累加不能恢复有限值，但此处没有实际数值/RTL验证此覆盖结论。
- 原始DDR/Scalar/Matrix错误进入poison/finish，传给client.abort；先排空已接收组债务及DDR/local/Scalar响应再发布失败owner完成；DDR仅匹配既有request.tag可退债，同拍故障与请求接受也记债。当前poison抑制新请求/score写，完成ACK后进入locked而不重复发布。组尚未接受时不制造done。
- foreign done不会清除债务；协议隔离可能需协调全局reset。done error不发布成功，也不允许下一key。
- score已写之后发生的terminal错误不能撤销该物理写；最终owner失败，禁止后继发布。该边界与原有“stage完成才交接”原则一致。

## 资源账本
新owner控制：packedOwned、packedFinalIssued、packedCommitted各1位，单调tag32位，另有DDR/local/Scalar三个已接收债务位，共38位。复用既有client53位，共91位控制寄存器；tag溢出0拒绝后续group。没有新payload寄存器、SRAM或fulltile copy。原有 acc16、Q local、scores/probs SRAM和DDR packet保持；不能把这些现有存储说成已迁移到raw共享banks。
client/drain状态、额外选择器、selected16值有限检查的组合逻辑尚未综合。冷模型的事件列表/对象不是硬件存储，也不是时序/算术模拟器。

## 下一连接缺口
1. 把单key馈送扩展为16key块，并明确Q/K bank/DDR实际端口调度。
2. core/kernel 尚无 raw-scratch 请求、generation、begin、lease、ACK mux；共享A banks路径仍需独立接线。
3. PV6和同context key16暂停、panel资源/写回lease尚未接入原始core。
4. 不可用本片替代 Python OfficialAttentionOwner 全程序资格；原始 Chisel算术/固定policy后续必须独立核对。

## 冷检查
在仓库根目录运行：
python -m unittest candidates.qwen2_resident_matrix.attention_qk_owner_route.test_route -v
python -O -m unittest candidates.qwen2_resident_matrix.attention_qk_owner_route.test_route -v
prepare.compose 仅组合已固定stream源与两个owner目标；包含原始seed服务依赖，完整Scala构建仍需原有项目闭包。逆补丁逐字还原两个原始文件；默认关闭的实际行为等价仍待后续elaboration/simulation，不能由文本逆投影单独证明。
