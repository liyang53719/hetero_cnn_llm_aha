# exact64 Q/K 诊断 fullblock 接线候选

默认入口只有 `NOT_EXECUTED`。`--actual` 和直接 `run()` 在任何模型、输入或
native library 加载前要求本候选专用 source-policy、两次 fresh reference
与独立预算；旧审批、已消费证书和既有输出不能启动本候选。尚未运行本候选的
完整 M128、RTL 或 CI。

## 本次边界

- pc1/4 接独立 `Exact64PublicDriver`/`Exact64ProjectionOwner`。accepted Memory
  beats 是唯一操作数，真实 64B output ACK 才允许终态。64 outputs × 64 FP32
  partials = 16 KiB；此独立软件 owner 尚未映射现 Chisel / MatrixStream。
  16 KiB 仅 partial；整个算术 owner 的保守 payload 为 23552 B，不含原
  PhysicalMemory 与入口/出口审计临时 n0 副本。
- pc7 V 保留原数学和原 ReductionDriver.run/tick；仅明确新公开 execution 类。
- Attention 保留原 PV32 全部数学，KV supply 改用已发布 resident owner 及同一组
  现有 A Banks。新 public publication authority 只能在十个真实 prefix
  completion 和 pc9 KvAppend publication 后 arm；入口/出口 hash、完整 ACK、
  generation、写保护门保留，连续 edge 不再重算全 KV hash。
- pc13..20 直接使用 tracked `qwen2_fullblock_ci_dut.tail.execute_tail`，不依赖
  未发布 `qwen2_fullblock_recovery`。所有 jobs 来自原公共描述符与真实 Host。
- 原官方 CPU profile、两份完整 fresh reference、原数值门及原 24 项数值聚合
  全保留；21 completion / 17 owner / 1 launch、无债务且实际输出 seal 后才
  读 oracle。没有 reference/provider 绕行。

任何通过仅输出 `PASS_DIAGNOSTIC_SOFTWARE_OWNER`，并带
`diagnostic_numeric_pass` / `diagnostic_acceptance_sealed`。
`fullblock_pass=false`、`acceptance_sealed=false`、
`chisel_full_prefill_pass=false`、`performance=NO_GO`、
`hardware_mapping=NOT_IMPLEMENTED` 始终保留。不能称现 Chisel 完整 prefill 通过。

## 计数与私有保全

`accounting.py` 分别核对 exact64 真正 kernel FMA/Add、旧 V Matrix accepted
steps、原 Attention 和原 tail。exact64 不增加任何 MatrixStream issue 或
4096-cell opportunity，也不把模型 tick 当硬件周期。旧 whole-block expected
常量没有被删掉：新硬门仅扣除移走的 Q/K Matrix work，并对实际所有 kernel FMA
与真实 Host terminal 总额做恒等核对。独立 tree Add 不冒充 MAC。

`retention.py` 在 oracle 开门前严格校验并登记 51 个本地文件：19 个完整 actual
输出、actual SiLU、全部十个 Attention 字段的 payload / presence / frequency、
原 observer receipt。特别保留 actual n1/gate/up/o/r/v，oracle 比较后再验证
文件未变。所有 raw、私有逐项 hash、shape、stride、path 与 receipt 留在新的
`work/` 输出，绝不上传；CI 销毁后不假定其仍可读取。

`gate_probe.py` 是另一个默认不执行的同 job postseal 阶段。在完整 RESULT、
LAUNCH、无债务、source/runtime identity 与上述 51 文件校验后，使用原官方
Qwen2MLP 的原样 gate constructor、完整原 raw BF16 gate weight 与同形输入。
第一调用必须用 fresh reference n1 逐 bit 复现其 gate，随后唯一第二调用输入
同次 actual n1。三组误差由原 `native.compare/stage_verdict` 给出：actual gate
对同输入官方 gate、同输入官方 gate 对 reference gate、actual n1 对 reference
n1；max/mean 不能相减解释传播。数字 FAIL 可以诊断；不完整、漂移或债务失败
必须拒绝。该阶段独立受两调用、120 秒 CPU/inner、122 秒 outer、2 GiB 限制。

`aggregate.py` 只读取固定私有 receipts，输出源中固定的数值聚合、布尔值及枚举；
原 120 门派生后增加新 scope、actual counters、全部新 debts/identity、保全与
postseal 控制门。任何 postseal 诊断不会改写主数值结论或赋予 formal PASS。
代码本身没有上传行为。

## 中文计划

1. 已写并冷测：独立 runner、诊断 scope、分拆计数、本地 actual 完整保全。
2. 已写并冷测：新 public21/shared-A binding、projection driver schema 与入口负测。
3. 已写：独立准入/ELF 来源门、专用 source closure、双 fresh reference、supervisor。
4. 已写：受限同 job postseal gate 隔离与严格 fixed-schema aggregate。
5. 待独审冻结：本次完整 source-policy、条件参考绑定、真实小批接线及完整执行预算。
6. 待新准入后：同刺激 fresh 完整 M128 单次执行并在同 job 完成诊断。
7. 后续硬件：五 context/frontier、Q/K exact64 与真实 Chisel/MatrixStream 接线，
   均未由本软件诊断实现。

冷测（也应使用 `python -O -B` 重跑；不加载权重、不编译或运行数值 kernel）：

    PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 python -B -m unittest candidates.qwen2_exact64_diagnostic_fullblock.test_cold candidates.qwen2_exact64_diagnostic_fullblock.test_binding_cold candidates.qwen2_exact64_diagnostic_fullblock.test_gate_probe candidates.qwen2_exact64_diagnostic_fullblock.test_aggregate candidates.qwen2_exact64_diagnostic_fullblock.test_admission -q

冷测使用合成微型字节和合成 receipts，绝不是数值 fullblock PASS。
