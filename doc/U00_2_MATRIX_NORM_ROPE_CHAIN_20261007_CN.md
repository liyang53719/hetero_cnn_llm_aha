# U00.2：实际 Matrix → Q/K Norm → SharedL2 RoPE 有界链（2026-10-07）

## 范围与不可替代的门禁

本轮在已有 `qwen2_projection_tile16_controller` 增加默认关闭的
`EXPERIMENTAL_QK_NORM_ROPE` 分支，复用 Revision8B-B 的实际 512-lane
Matrix endpoint、已验证的 Norm256 与 all-products-BF16 RoPE 候选。
不另建架构 top，也不切换旧生产路径。

每次命令只执行一个 token 的一个完整 Q256+gate256 或 K256 头：
原始 H1024 BF16 激活与所选权重经 DMA/真实 SharedL2 输入 Matrix，按 K0..1023
顺序 FP32 FMA 累加，末端 BF16-RNE；content256 进入 gamma=1+weight 的 Norm256，
经 SharedL2 写 ACK 后由 partial64 RoPE 读取，192 维尾部按原位保留。
Q gate256 留在原 packed projection 中，不参与 Norm/RoPE。

这不是全 Q8/K2、多 token owner、完整 Command128 端到端集成或完整 block。
系数从明确 BF16 cos32/sin32 输入；位置生成/cache、KV 提交、Attention 与 FFN
后续路径尚未接通。固定三模型完整 block 数值与整 block useful-wall MAC≥90%
仍 OPEN；U00.2 ongoing，U01 to do。Matrix/Vector 的性能口径不变。

## 来源与独立数值检查

只从固定官方 checkpoint 的临时本地 payload 重新执行 baseline/AVX2 官方前缀。
每套使用 cold token0 的 Qhead0/Khead0，以及 carried token127、position255 的
Qhead7/Khead1，合计八个选定 head 用例。人工 token 序列的来源边界保持原说明。

整数 dyadic oracle 从实际 preprojection activation 和原始 BF16 权重计算，
不读取 native projection 作为任何硬件阶段输入；独立 C fmaf 复核全部
3,145,728 个累加器值及末端转换，Norm/RoPE 继续使用独立 C 节点检查。
这些选定 head 的 native projection、gate、Norm、RoPE 均逐位一致，原精度门限不变。
完整 producer audit 仍有拒绝项，选定 head 通过不能覆盖整 block 失败。

## 事务与物理容量合同

- 真实 `shared_l2_fabric` 使用 4×6144×64B，即 1,572,864B；地址总线15位不等于2MiB容量
- 全部命令/sideband 在接受时快照；后续外部值扰动不得改变事务
- activation/weight 各64KiB staging 与 packed、gamma、Norm、trig、RoPE 区域必须对齐、无重叠且在实际容量内
- 65位中间地址检查避免高位回绕；DDR输出不得覆盖后续 selected weight 的保守跨度
- 每个 DMA、L2 read/write 只保留一个 owner；错误状态跨 done/idle 锁存到下次合法 start
- 叶模块写 ready 由 ACK 驱动；packed store 的 DMA ACK 必须完成后才能开始 Norm，Norm 写 ACK 后才能启动 RoPE，末端 ACK 后才 done
- reset 必须同时清空外部 fabric 的旧响应；不保证对已经写入的数据回滚或事务原子性

## 可复验入口与提交政策

`python scripts/run_matrix_norm_rope_candidate.py --output work/matrix_norm_rope_candidate_result --jobs 2`

该入口重新物化官方输入、重发射未修改生产 HardFloat 算术、编译实际 Matrix512
与真实 SharedL2，运行 baseline/all 和 AVX2/main。JSONL 独立消费器逐项检查累加器、
Norm/gate、DMA 几何、读写内容、ACK owner、done 与完整用例库存；只有日志 PASS 不足以验收。
工作开始/结束都核对源码、生成硬件和临时向量哈希。

Git 只提交源码、固定来源/哈希和简短结果摘要；所有 checkpoint、NPZ、memh、
完整事件轨迹、生成 RTL 与二进制保留在忽略的 work/ 中。CI 仅上传 summary.json，
继续保留当前 payload guard，不修改历史。

## 验证记录

最终fresh RTL回放与全部来源复核已通过 `PASS_BOUNDED_MATRIX_NORM_ROPE_RTL_CHAIN`。
摘要为 `reports/execution/U00_2_MATRIX_NORM_ROPE_CHAIN_20261007/result.json`，
独立复核为同目录 `independent_review.json`；后者核对原始最终运行摘要，SHA与result中的summary_origin_sha256一致。

- baseline/all：45事务，7成功、21拒绝、10真实transport故障、7reset，291个明确L2写ACK
- AVX2/main：4个选定head成功，49,152个Matrix输入/输出包及112个明确L2写ACK
- baseline输出141,319包，比输入141,320少1包，仅在Matrix reset用例中有意清空在途第8个输入；每个正常done均已排空owner
- 独立trace消费器完整校验上述库存、逐K FP32值、Norm均值/逆平方根/flags、raw gate、DMA地址及L2实际数据
- 所有primary八例共3,145,728个Matrix累加器值均由整数/C参考绑定；native选定头逐位一致
- actual generated RTL SHA256：`5d4cf714637a579a50b9fd79eed3569c7e2a2bf39de9ba27775f0eb41d31aaf6`
- baseline仿真507.539s、AVX2仿真181.039s是工具墙钟，不能充当硬件性能/PPA或整block利用率

最终回放前后源码、临时来源向量和生成RTL manifest均重新核对；旧生产默认不变。
本轮恢复过程修复了trace字段/字符串填充/库存/实际done观察，以及Norm/RoPE在途reset的测试缺口，
不会用较早不完整的回放日志替代以上最终证据。

本轮源代码回归：全仓 2867 passed、5 个既有失败，失败名单未变。197 个新增候选/
runner/独立trace测试在 normal 和 -O 下通过；已有 Norm/RoPE 的631项 normal和-O回归通过。
旧默认关闭路径的独立RTL检查另覆盖两种decode模式各8例、writeback10例/15360值、
iterator尾部及拒绝、descriptor规划3072tiles，省略候选依赖的默认source-closure lint通过。
计划和清单一致性校验通过，均不代表完整硬件目标已验收。

同周期 L2 write ACK 的专项用例、链级算术非有限/溢出拒绝专项，以及综合/PPA
尚未在本轮验收；本轮协议故障以实际 descriptor、DMA 和 L2 错误响应为界。
