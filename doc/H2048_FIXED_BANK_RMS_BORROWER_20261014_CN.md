# H2048 固定三 bank RMS：生产 core 服务借用

后续更新：本文保留首批未加内部计数的回放边界。2026-10-14 已完成同 bank Scalar/Vector M1/M16/M128 A/B、真实执行拍及互斥周期分解，见 [同资源性能回执](H2048_RMS_SAME_BANK_PERFORMANCE_20261014_CN.md)；首批日志不回填新测量结果。

## 当前阶段与边界

本批承接 main `3cd847d32008eac4916c2691fbe0265df8859481`。该基线修复真实 fixture suite 的显式分类；未把缺失外部输入的测试记作 PASS。本文仅记录 H2048 RMS 子链，不升级完整 35B L0/L3、完整 block 或 MAC 利用率结论。

- 已通过：synthetic M1 独立生产算术模块的 Chisel→RTL→Verilator 数值和协议门。
- 已通过：复用生产 `Qwen2ContinuousBlock` 内原 Scalar、原位置 `core.elem` 的 M1 synthetic 数值、写 ACK、abort、wrong-tag drain 门；同时保留原 RMS 小宽度回归。
- 已通过：冻结真实 postnorm 输入 M1（原 M16 第 0 行）、M16、M128 的整条 RMS 算术链。只向 DDR 输入原 BF16 input/weight，绝不注入 observed inverse。
- 已通过：H1024 原 Scalar 路径数值回归，真实 loan poison 后不依赖全局 reset 的恢复，以及真实同时 owner/loan 竞争与 held-terminal admission。完整 kernel 两分支 elaboration 和修复测试名称解析后的资源库存检查也已通过。
- 后续性能实验：同刺激、同银行和同 DDR 策略的 Scalar epilogue 对照；互斥周期分类及实际 ALU issue/lane 统计。没有对照时不报告加速比。

统一目标仍为 Qwen2-1.5B 完整 block、0.8B L0/L3、35B L0/L3，主 workload 为 prefill128。阶段模型优化要求是固定资源、完整墙钟周期分母下最低 80%、争取 90%；最终实际完整 RTL 的 90% 联合验收目标不变。前三类已有指定 M128 typed 软件门；35B L0 目前仅到 postnorm，router/MoE、35B L3 和完整数值 RTL 仍未完成。

## 固定资源和算术

`GdnRmsNormFixedBankOwner` 的 logicalWidth=2048 与 bankWidth=1024 分开。input、weight、output 各 32×512 bit，即三块各 2 KiB，总 6144 B。output 的前 128 B 在归约阶段覆盖为 32 个 FP32 residue partial，inverse 完成后该 overlay 退休并复用为最终 BF16 output；没有新增 partial、gamma、normalized 或 loan-result 数组。

保留四个 FP32 标量寄存器。归约按 8 lane ×4 residue ×4 block ×16 term 的原 FP32 独立乘法/加法顺序，两个 input chunk 分别读入原 input bank。所有归约、mean、epsilon、sqrt、reciprocal 由真实 `BlockScalarFloat` 计算。第二遍按 chunk 重读 input/weight，再借用原 elementwise 16-lane ALU 做 normalize→gamma→weighted，最后一次 BF16 RNE 后写原 output bank。

每 token 精确事务数：

- 4268 Scalar：2049 MulIeeeRne、2217 Add、1 Sqrt、1 Div
- 128 次 16-lane loan，384 次向量 primitive issue
- 192 次 64B 读，共 12288 B；64 次 64B 写和成功 ACK，共 4096 B

每个 output chunk 填满后才开始写；最后一个真实 ACK 前不能复用该 chunk 的银行或发布整个 job。M128 实测为 546304 Scalar、16384 loan、24576 读和 8192 写 ACK。

输出银行从 1024×16 改为 32×512 的寄存器组织，容量相同不证明物理 banking/端口/布线相同。并行 BF16 舍入和选择网络也有组合成本。没有综合、STA、面积或 SRAM 推断验收。

## 生产绑定和默认兼容

新增 `externalElementwiseLoan=false` 与 kernel 内部 `enableH2048RmsBorrower=false` 编译选项。旧 H1024 owner、原默认 profile 和 public Host admission 均保留；启用时静态二选一，不能同时实例化两套 RMS 银行。

新 core 分支在原 `elem` 位置选择 `ElementwiseRegisterLoan`，保留原 `ChainConfig()` 和 `LocalSramConfig(rowsPerBank=elemCfg.localBytes/256)`；没有第二个 elementwise engine 或 Scalar。当前生产 core 的 `elemCfg.localBytes` 为 12288 B，不能混同此前 standalone lender 的其他配置或全 SoC 总存储。

core 本来另有 legacy vout16；这次的准确结论是复用 core.elem 和 Scalar，不能说整个 top 只有 16 个 ALU。已生成的小 shape 生产 core RTL 显示 core 本身的 vout16、一个 Scalar（内部1个ALU）及一个 lender（内部16个ALU）。本批没有改变 Matrix 配置或声称完整 Matrix4096 活跃。

kernel mode8 在构造新 typed job 之前检查三个 BF16 标志、n=k=2048 及 writeBytes=m×4096。原 `QwenBlockShape` 的 native H1024 约束不动；这是内部 RMS 子链选项，不是完整 H2048 model profile 或新的 public command。

## 排空、失败和恢复

memory/scalar/loan 同时至多一项 owner 债务。已 offered 的 request 背压或取消时保持 payload/valid；已 accepted 的 request 必须等待真实匹配返回。

- wrong-tag packet 被消费并记录 Protocol，但不解除匹配 tag 的真实债务；若真正返回永久缺失，不伪造 drained。
- abort 后真实成功写 ACK 仍计 staging bytes，但输出不发布。
- loan offer 取消时先握手，然后一次 abort pulse，再拉低 abort 接收 Aborted terminal；不能用 sticky poison 驱动 abort。
- 成功 done 被背压期间仍有 task 所有权；与 abort 同拍时禁止成功退休。
- 失败 done 退休后锁住新 job。clear 是显式外部 recovery/stale-response 排除声明，不能擦除 held terminal 或未排空债务。
- loan-origin poison 可在 drain 后通过 resetLoan 恢复；DDR-origin poison 或其他 kernel 故障不由该接口清除。
- 一次恢复尝试发一个 resetLoan pulse；调用者应使用 pulse-clear。持续保持 clear 会在返回 idle 后再次进入恢复，始终阻止新 admission，不应宣称每次持续断言仅一个 pulse。

core admission 包含尚未握手的 loan offer、busy、held result、poison 和恢复控制；kernel 保持 active/mode 直到 done.fire。仅新 loan request 使用 active/mode 门，terminal、busy、poison、abort/resetLoan 不被该门切断，保证失败终态后仍可恢复。

## 当前实测回执

首个独立 M1 成功和后继生产 core 服务 M1 都得到 19893 owner cycles、4268 Scalar、128 loan、192 读和64写 ACK。此周期包含测试中明确的人为 DDR/Scalar/loan 背压，不能作为无停顿延迟、整 block 性能或相对原路径加速比。

成功数据逐项比较所有 Scalar 请求 opcode/operand/result、所有 loan 输入/真实 inverse/FP32 weighted result、每个 BF16 write beat、真实 write ACK、末 ACK fence 和 held done。wrong-tag loan 使用真实 held arithmetic terminal 复制仅改 tag 的 stray packet，原匹配 terminal 仍保留到稍后真实退休，不假装错误 packet 已解除债务。

首轮保留三个失败：Scala enum 换行解析、Bool.asUInt.pad elaboration、TB 周期性背压没有保证命中 loan request。前两项修复未改算法；第三项改为确定性首事务背压并保留原“必须观察到 stall”断言。不存在用放宽数值门、取消测试或注入参考结果换取成功。

`work/h2048_core_first_gate` 的 2 suites/2 tests、零失败/skip；该轮冻结并核对所有仓库 Scala 源。原 RMS 回归使用 width32，不将它说成 H1024 实测。完整源/fixture、日志、生成 RTL 的最终回执由 `scripts/run_h2048_rms_borrower_tests.py` 留存于 ignored work。

首个真实进程中的 M1 和 M16 case 已分别完成全部断言并记录成功，M16 为 317642 owner cycles、68288 Scalar、2048 loan、3072 读、1024 写 ACK。随后发现测试器将 Iterator.toSeq 展平为 List，546304 项 trace 逐索引访问造成平方级宿主工作；独立 Scala2.13 类型探针确认后有界中止该进程，整体标记 INTERRUPTED_TB_QUADRATIC_LOOKUP，M128保持未完成而非PASS。原源码及fixture前后hash一致，测试源码按原hash回存可重建快照。修复仅改用不可变Vector/IndexedSeq并增加indexed类型断言；DUT和参考FP32次序不变，只续跑M128。

修复后的 `work/h2048_actual_m128_indexed_gate` 在冻结同一份 M128 刺激下通过 1 suite/1 test，源码和 fixture 前后哈希一致。实测 owner cycles=2540814，接受 launch 到 done.fire 的边沿间隔=2540828，含 13 拍人为 held done；逐拍采样总数=2540829。M1/M16 的原独立结果仍保留，原中断 suite 不追记整体 PASS。M128 manifest SHA256 为 `799a8e3bc67c1dd32a77cc4766268a4d5c570639cf1fb7a18f87153fe008fde7`。

M128 的 16384 loan 可按协议推导 49152 个 16-lane primitive（Normalize Mul、Gamma Add、Weighted Mul），即 524288 个标量乘法加 262144 个标量加法，共 786432 个 FP32 lane 操作；这不是 MAC，也不是独立观测的 ALU 忙拍。当前版本尚未测量 ALU 执行/忙拍/有效 lane-cycle，loan 接受率 16384/2540828 也不能替代 ALU utilization。下一批使用原 ALU 状态/信号的测试观测和同资源 Scalar epilogue 对照，补齐互斥周期分解。

补充 release 门中，两个 cancellation suite 验证 real Scalar pending、受背压 loan offer、held success terminal 的取消，错误 tag 不解除真债务，真实 lender poison 后 pulse-clear、不用 module reset 的两次恢复和再次完整计算；core admission suite 完成 1 个真实 DDR Add（2读、1写ACK、1stage commit）与两次 loan 的序列化。默认 H1024 原路径逐项检查 5124 个 Scalar 结果，20491 owner cycles、2048 acknowledged bytes，通过 synthetic 数值门。

该五测试批保留 4 pass/1 fail 的原整体失败状态：结构 TB 名称正则遗漏 Chisel 自动生成的 `_1` 等后缀。实际默认/启用 CHIRRTL 都有 33 个 HeteroFP32Alu 实例（Scalar1、legacy vout16、elem16）和 66 个 SRAM 声明；仅修正正则后单独重跑结构门，1 suite/1 test 通过；不把测试解析问题报成硬件丢失 ALU。

## 真实数据复现入口

`prepare_h2048_borrower_replay.py` 只复制或切片已冻结 actual observations，不运行模型或计算 FP32 参考。要求外部预先固定 producer summary SHA；101 prefix 源、9 owner 源、13 native artifact 和所有实际观察都须校验。30 项冷门覆盖源漂移、错误 pin、路径逃逸、非 actual 节点、错误形状、weight 非无损 BF16、真实输出/RNE 不一致等。

实际 M16 producer summary pin：`368aa8ec2a5b5ac98a79bb24ca5fe718b4a7ab0cf90e9268c261851e2a98501d`；M128：`acd9b3e99654c72a1d868dd9eb079ac255ecb0be76bfebbe21a3e491a4556f07`。inverse 及所有 FP32 节点放在 expected/，只有 stimulus/input.bf16le 和 stimulus/weights.bf16le 能进入 DUT memory responder。

实际 replay suite 被显式分为 `frozen_actual_h2048_rms`。普通 continuous CI 对其标记 NOT_EXECUTED_REQUIRES_FROZEN_ACTUAL_FIXTURE、counted_as_pass=false；专门 runner 缺 manifest/env 仍硬失败。权重、可重建 raw、ELF、生成 RTL 不入 Git。

## 性能结论限制

当前 borrower 仅移走 RMS epilogue 的每 token 6144 次 Scalar，归约 4268 次仍留在 Scalar。它只消除此前测得 35B prefix Scalar 工作约 7.04%，不能称为已经解决整个 block 的低利用率。完整模型预测、局部实际 RTL 和完整实际 RTL 必须分栏报告，固定 Matrix/Vector/Scalar 分母和 stage/DDR/末 ACK 间隙不能省略。

## 本批 CI 分类与触发审计

七个 Host workflow 保留全 main/test Scala、build、resources 和未知工程路径，只排除三个与 Host 执行无依赖的精确 continuous planner/runner 文件；补上 classifier/verifier 冷测试触发路径。当前 Qwen2Block/QwenOwnerProtocol 生产更改仍应触发七个 Host。没有取消运行中任务，没有跳过受影响门禁。旧 planner 冷测试遗漏 external fixture 的问题同步修复，external suite 必须唯一专属分组，缺失逐个硬失败。

局部机器回执见 `reports/execution/H2048_FIXED_BANK_RMS_20261014.json`；原数值刺激、失败日志和生成物仍在 ignored work，没有权重/raw/ELF 进入 Git。
