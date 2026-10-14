# 35B L0 Chunk 单 1KiB 四行复用候选

## 状态
- done：局部冻结 scratch 重放已随 d2c93daf 发布；真实 owner opt-in 路径及错误/排空/重置小门已实现。
- done：M16、M128 同次真实生产者链及独立逐字节/计数复核完成。
- ongoing：小批发布及原触发 CI 工件闭环。
- todo：生产 Chisel 绑定、完整周期时间轴与 MAC 忙占空比；MoE 及完整 block 仍未闭合。

## 实际控制与资源
显式 row4_shared_1kib 策略同时绑定 job、owner、driver 资源身份和终态源码身份；旧 row1_streaming 默认保持。transpose 与六处 matmul 互斥借用同一 256×FP32 buffer，reset 在排空后复用原对象。matmul 划分 A 256B、B 512B、累加 256B；transpose 借用全部 1024B。每个输出仍按升序 K、分离 FP32 Mul/Add 运算，factor 在归约之后；无新增并行阵列。

成功、abort、read fault、write ACK fault 都不能在已接收写响应之前释放 scratch。末写 ACK 背压保持租约；held-success 遇 abort 不发布输出或状态。失败终态后 reset 不丢失未退休义务。局部 scratch 的显式上界不等于整个 Python generator 局部变量已经有完整 Chisel 寄存器映射。

## 预测与验收边界
六处 matmul 以四个输出行复用 B；只减少 B 读取，A、factor、写入/ACK、Vector 运算数、所有 FP32/BF16 舍入保持。完整维度 M128 预测 chunk 读 1,483,079,680→577,110,016B，减少 905,969,664B；M16 减少 452,984,832B。closed_counts 保留旧默认，并与实际缩维 owner 的读取、写入逐字段比较。

以上闭式运输流量预测已与本批两档真实链终态逐字段核实。typed transport ticks、宿主秒数、Vector 调用不等于硬件周期。固定 4096 Matrix MAC、16 Vector lane、1 Scalar；80%/90% 为完整 block 目标，当前不能报告已达到。统一时间模型仍缺新 Scalar/Vector 策略生产映射和完整 block 的共同时间轴。

真实验证必须同次实际 RMS→QKV/Conv/A/B→Prep→Chunk，不从旧 raw 注入生产者；旧 raw 仅事后逐字节比较输出、state、scratch 和下游结果。history/state 保持 private staging/generation 0；本批不授予新的数值容差。

## 本批预检失败记录
1. 首轮相关 37 项回归中，旧源码身份测试未列新增 matmul_reuse.py；同时测试进行中模块说明被修改，warm 事务按设计拒绝 source_changed。两项修正/冻结后同 37 项全部通过，原日志保留。
2. 首轮全冷运行未导出固定 Matrix 库/receipt 环境，相关套明确拒绝执行；另发现 core-only 发布边界仍硬编码旧资源元组。已补齐新策略、buffer 身份及无租约检查，保留严格准入，并增加 legacy 与 ROW4 两种完整运输/下游失败测试。该首轮不计通过，带原固定库的第二轮已全部通过。
3. lease 错误/尾 ACK 小门中的 transport script 用于精确注入协议边界；另有真实缩维 owner 数值测试。不能把 scripted fault 当成真实完整维度算术故障轨迹。

## 冻结验证进度
- 第二轮最终冷门：728 tests / 76 suites，零 skip，全部成功，source unchanged。第一轮失败记录继续保留。
- 01:41 UTC 启动 M16 同次完整前缀，内部 wall 1800 秒、外层 1830 秒；该次已终态 exit 0 并独立核验。
- 即使预测流量全部兑现，13 阶段单共享 64B payload 下界仅由 25,777,928 降至 11,622,152 槽，条件 Matrix 利用率上界 4.08%→9.06%；原单 Scalar 基础请求 II3 下界未变，对应更紧的 1.57% 条件上界仍在。需要继续处理现有 Vector lane 上的独立元素并行映射和真实共同时间轴。以上只适用于当前前缀与既定映射，不是完整 block 或 RTL 实测。

## 后继 Scalar 瓶颈的生产资源约束
QwenOwnerProtocol.scala 的 bf16GdnCore 配置没有实例化 ScheduledSiluOwner；不能把 VectorSilu 模块内部 16 个 BlockScalarFloat 当作当前 GDN 已有资源。后继应针对真正存在的 Vector16 Add/Mul ALU 增加有限寄存器 loan/control 和 IEEE op6 异常语义绑定；先局部生产测试，再评时序收益。两次 RMS epilogue 的 1,572,864 lane 操作或 Conv 四 tap 的 8,388,608 lane 操作可作为依赖候选，但当前未实现/未计收益。H2048 RMS 必须沿现银行和生命周期，不能把生产 H1024 数组直接翻倍。

## M16 实际结果（已独立复核）
01:50:21 UTC exit 0，101 执行源码前后及当前哈希一致、13 native 身份核实。27 个实际 raw（包含全部 scratch、state、FP32 节点）逐字节等旧批；16 个观察和13个成功终态完整。Matrix整报告、全链Scalar和Chunk Vector issue/lane/flags全部不变。

Chunk 实际读取739,344,384→286,359,552B，其中 scratch285,540,352B，source819,200B；写30,146,560B不变，运输ticks24,046,593→9,890,817，与闭式预测完全相符。单tile高水1024B且终态lease为空；generation未推进，history/state私有。M16有效行仍16，Matrix物理M128填充不变，不把它算128token验收。

复现事后比较：运行 scripts/compare_qwen35_chunk_reuse.py，指定 --tokens、--baseline 和 --candidate 两个完整原报告目录。该脚本核源、native与实际文件字节，写 reuse_comparison.json；不运行模型，也不注入原raw。

## M128 实际结果（已独立复核）
02:12:10 UTC exit 0，101 源/13 native 前后身份成立；27 actual raw逐byte等旧attempt3，16观察/13成功终态完整。Chunk读1,483,079,680→577,110,016B，scratch570,556,416B、source6,553,600B、写56,885,248B；减少905,969,664B，运输ticks48,123,905→19,812,353。完整53,739,520B scratch和state也逐byte不变。

Matrix实际FMA两档均4,311,744,512；M16算法有效538,968,064、M128有效4,311,744,512，对应有效/执行工作量比12.5%/100%，这是填充效率，不是时间利用率。全部Scalar/Vector调用及lane运算保持。当前前缀M128实际总read671,891,968B/write71,925,760B，已重新代入原条件分析脚本得到11,622,152 payload槽下界和9.05746% DDR-only上界；更紧的Scalar-only1.56996%仍在。硬件周期、忙占空比、完整block利用率均未获得。

两档宿主时长554.3946s/1238.8757s仅为执行记录；不据此声称硬件吞吐改进。原有数值诊断范围不扩大，生产Chisel未绑定此ROW4调度。
