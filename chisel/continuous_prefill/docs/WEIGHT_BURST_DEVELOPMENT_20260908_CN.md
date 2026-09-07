# 4096-MAC real16 双层：冻结基线后优化权重供数

冻结基线的完整验收已完成：被测 d3571eec，发布 3118b183；42 条 Host 命令、430 descriptor、38 owner 作业、1,409,024 个 FP32 输出与原 512-MAC 实际输出一致。

基线周期 114,418,263；按 800 MHz 换算 143.02282875 ms；对 512-MAC 的 146,854,495 周期加速 1.28348824 倍。有效 MAC wall 利用率为 0.319679735%，不是 98.30%；后者只是 useful/executed 比例。800 MHz 是目标频率，未签核 DC。

## 第一项优化：有界、只读、作业内的权重突发供数

新增 Chisel `RetainedIdmaWeightBurstAdapter`。仍只有一套真实 pinned iDMA；没有旁路 AXI 算法，没有 Host 计算。每个 Dense 作业从已经校验的 descriptor 取得只读权重基址和限界，最多读取 16 个 64-byte beat，保存于 1 KiB mailbox。裁剪至 tensor 范围、tensor-relative 1 KiB 边界和物理 1 KiB 边界；最后一项适配保留 iDMA 的 max_llen=4，并自然满足 4 KiB AXI 边界。

只有整段 iDMA 成功后才能命中 mailbox。任一 beat 报错都会使整段失效，先排空既定响应，再向原 requester 返回错误。新 owner、新请求及写操作失效旧缓存。metadata、激活和写回仍走原单-beat 合同。它不是 whole-object cache，不跨请求持久保留。

原 4096-MAC、Host 编码、权重存储、FP32 容器、计算及 K 累加顺序均不变。模式通过 `WEIGHT_READ_BEATS=16` 显式启用；缺省 1 保留旧路径用于对照，未用未完成的长仿真自动替换默认生产验收。

## 已有开发证据与限制

沙箱使用实际 Chisel 生成 DUT 和同一 pinned iDMA：24 项供数/边界/错误/复位测试通过；新路径 tiny real-DUT 两层 42 命令、39,936 个输出通过。该 tiny 配置是 H64/F128，不是 H1536/F8960。真实尺寸双层优化后最终性能，以 `WEIGHT_BURST_COMPARISON.json` 为准，不能用 probe 加速比或 tiny 结果外推。

C++ AXI memory service 新增 burst response 序列。保留原每-beat 1..5 周期随机响应延迟、AR/AW/W 回压和 completion 回压；未通过减少 RAM 延迟美化结果。计数明确分开 read beats、read bursts、iDMA transfers 与 cache hits，要求完整输出和物理/逻辑字节守恒。

## 执行 agent 只复核、执行

```bash
export IDMA_EXPORT=/absolute/path/to/verified/idma_export
bash chisel/continuous_prefill/scripts/run_weight_burst_real2_gate.sh /absolute/new/weight_burst_real2
```

无需修改源码、生成 RTL、数值阈值或参考程序。缺工具为 77/BLOCKED，其他失败返回开发侧；保留所有工件。成功需要 gate.exit=0、numerical/simulation.exit=0、完整双层输出比较通过以及 `PASS_WEIGHT_BURST_REAL16_TWO_LAYER_EXACT_COMPARISON`，不是只看 CI 绿色。

不扩展 32/33 token 或新模型。后续优先增加实际供数/issue/wait 计数，再处理 operand 双缓冲和多 context pipeline；不以裸阵列 II=1 代替整请求利用率。错误 RLAST 的排空测试提供完整已承诺的 R beat 数；真正提前中止而不再返回的外部总线属于系统超时/复位合同，未宣称恢复。
