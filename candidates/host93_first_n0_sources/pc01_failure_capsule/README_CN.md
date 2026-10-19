# PC01 首个 identity 失败的固定标量胶囊

范围：SOURCE ONLY。5 个生产文本（新增 1 个 header、窄改 4 个原件），未编译 C++、未重链、未执行 RTL。原 PC1_022、8 个谓词及其短路顺序、原 resetRequired guard、时钟/握手/退休/资源预算完全保留。PROJECTION.json 可逐项逆向恢复四个原件。

## 已知失败与未知项

原实际只有 RTL_PC1 / CONTRACT_ERROR / PC1_022 / numeric_comparison=NOT_RUN；无 counts 或数组。PC1_022 聚合 8 项，原证据不能指出具体失败项或 low/high 时点。本补丁不修改原 FAIL，不重构缺失的实际值，不给根因结论。

ACK0 高边沿已有 resetRequired=0 门（原 n0_model_scheduler.inc:190）；进入 PC1 前 Pc1ProductionGuard 的构造/profile/identity 再检查（原 pc1_production_guard.hpp:34–39、81–85）。正常成功 ACK0 分支只有记账、pc++/fetch，没有“ACK0 必须置位 resetRequired”的语义。后续新的服务/协议故障能够把该聚合信号置位。已冻结实际 Host93 profile 没有启用 H2048 RMS borrower，不能套用其他 profile 的 vectorUnavailable 分支。仅据本次聚合错误无法在观察器过约束与 RTL 实际故障之间定案。

## 原 8 项的来源（原件行号）

固定原件均在 SOURCE_PINS.json 逐项绑定，以下 include 路径相对于原 pc01_bridge/bridge：

1. owner.phase==Runtime：runtime_ram.hpp:41、50 定义；finish/take_runtime 的 :458、462 转移进入 Runtime，checked():62–65 和 adapter 析构在异常清理时可改 Poisoned。
2. owner.published：runtime_ram.hpp:60 初始 false；原 N0 publication :368 在 ACK0 完成后设 true。
3. !owner.qraw_published：runtime_ram.hpp:57 初始 false；pc1_retirement_adapter.inc:55 只在最终 ACK1 之后由 publish_noexcept 设置。
4. model.rootp 非空：唯一具体模型在 pc01_driver.hpp:19–21 构造；原 guard :34–39 另有同一 root/Syms 和 clock/reset alias 身份检查。
5. !model.reset：pc01_driver.hpp:23–33 是唯一 reset 初始化/释放序列；后续 Pc1ModelScheduler::drive 不写 reset。
6. !model.io_resetRequired：是真实顶层聚合端口；n0_model_scheduler.inc:190 与 pc1_production_guard.hpp:38 已检查，不能解释为普通 ACK0 状态。
7. !context.gotError、8. !context.gotFinish：同一 pc01_driver.hpp:19–21 的唯一 VerilatedContext；timeInc 只推进时间。原官方 Verilator 的 stop/fatal/finish 路径可设置状态，当前没有实际逐位快照，不能把正常初始化值当失败时实测。

原复合式唯一在 pc1_model_scheduler.inc:33–36；原四次调用在 :101、102、127、128。原 main:85 调用抛出后，:88–94 的数组/counts 写出未执行；:105–106 清 output_fd 后仅打印有界错误码。这解释了证据缺口，不补造原数组或计数。

## 最窄补证

- main 在 try 外持有固定 POD；driver 完成原 ACK0 强门并计算原 N0 hash 后，仅复制 6 项计数和已有 32-byte digest。没有第二次 hash、张量副本或离线 N0 加载。
- 四个 identity 调用点标为 SETTLE_ENTRY、LOW_EVAL_POST、RISE_ENTRY、HIGH_EVAL_POST；edge 是本次函数实参。SETTLE_ENTRY/RISE_ENTRY 是函数入口，不假称新的 eval 已发生。
- 8 项原表达式仍顺序短路。known_mask / true_mask / first_false 由实际执行到的 probe 记录；未到达的后项输出 null。原 require 前冻结，随后仍抛同一原异常。
- checked() 及 adapter 析构可把 owner phase 变为 Poisoned。胶囊在此之前只冻结一次；外层 catch 不再读取已析构的 model/owner，更不把清理后的 Poisoned 当成首因。
- root_valid 表示非空且与构造时同一 root；无效时所有模型端口和 root 标量输出 null。context_valid 独立记录非空且同一 context；胶囊采样函数不解引用 context，gotError/gotFinish 只来自原谓词的已求值位。没有为原 identity 增加新的 context 放行路径。这里不承诺从任意无效内存或进程崩溃中恢复。
- 仅读取现有 guard 已注册的 owner/router/core/hub/DMA/writeback 聚合状态，以及 matrix steps/wideSteps/stalls/state/mask/valid/ready/legal/poison。没有新 RTL 探针、未注册内部 tile 字段或连续 trace。
- pc1_jobs/dones/acks、B、committed、cycles 是软件已经完成的退休计数。HIGH_EVAL_POST 在当次 high 的验证/记账/commit 之前；此时端口可能已变化，而软件计数尚未包含该边沿。accept_edge 只在 pc1_jobs>0 时有已接受含义；ack_edge 只在 pc1_acks>0 时有已接受含义。

## 输出和异常优先级

原 1 行终态 JSON 保留。仅有首个 PC1_022 快照时，之后补 1 行 PC01_IDENTITY_FAILURE_CAPSULE_V1 JSON。固定 8192-byte 栈缓冲；POD 编译期要求不超过 1024 bytes。格式截断或 fwrite/fflush 返回错误只会丢失补证，不能改原 status、code 或 exit；胶囊不能授予执行或发布权限。没有任意异常文本、地址、路径、数组值。N0 hash 是 ACK0 时的已有内存观测；numeric_comparison 始终 NOT_RUN，root_cause 始终 null。

成功路径无胶囊行。其他错误码也没有新增快照覆盖承诺。native 异常退出后，原输出目录和日志保留策略仍由已有调用方负责；这里不重开已关闭的 output fd，也不保存张量。

## 后续边界

本批只做 Python 纯 mock 和固定源字节/逆投影测试，不能证明 C++ 编译通过、实际吞吐或 RTL 根因。原 28-source 树需未来明确组装为 24 个原件 + 4 个替换 + 1 个新增 header，共 29 个；原固定 28-source 重链入口不能直接冒用。后续如获准，可只重新编译/链接 driver 并复用同一已验证 archive，但需要新的源码/ELF/receipt 合同。

失败进程已退出，没有可恢复 checkpoint。任何后续 PC01 实际验证都必须 fresh reset、同一 Host/context/RAM 从 PC0 重跑到 ACK0，再继续 PC1；约一个 N0 的既有成本需要重新承担。此处没有长 RTL、重链或重跑授权。
