# DerivedAndPair 独立 owner 接口与状态合同（仅源码实施）

绑定 1605 只读审计与 1616 独审收口。只实现 chunk64 phase2，不改公共、Host、recurrent 门，不实例化或修改任何算术服务；无编译、构造、握手、数值或 RTL 资格。

## 输入与私有结果

- job：原 GdnChunkJob context、16-bit head/chunk、phase1Context（可信 scheduler 保存的 phase1 accepted context）、原 GdnChunkLoadPrepResult phase1Ready。
- 额外 phase1Context 是明确的 scheduler 包装，不冒称 phase1 原结果已有全部根字段。准入逐位等于本 context。phase1Ready 必须同 tag/generation/head/chunk/phase1，Ok、stageComplete、drained、64 Add requests/results、102400 scratch ACK，output/state ACK=0，实际有效行数×25×64 的 readBytes。原 phase1 已检查完整 prep 与 initial/前 chunk16+17 依赖；scheduler 必须保证来源链及全job源/根独占稳定。
- 原 GdnChunkCommittedState 仅在 job.fire 取样并验证。完整五 span 对齐、56-bit末端、别名、M16/M128/head/chunk/generation 与 legacy policy 均检查。
- 新私有 decay 结果保存完整 accepted context、head/chunk、value/valid；仅最后 pair ACK 成功且所有固定请求/成功结果/ACK计数齐时有效。scheduler 独占保存至同身份 phase15，失败不能使用，不自动发布任何 root/generation。

## 原接口借用及恢复

- MemoryRequest/Response 原 ABI；只有64B full-beat request/mask，没有 response nbytes。
- GdnScalarClient 原 ABI，只 ExpNegative4，b恒+0；无 tag/rawflags，依赖独占且无旧响应，不伪造隔离/防重放。
- Flipped(ElementwiseLoanPort) 原 ABI，只 Add1/Mul2。Add lane0有效，其余15个+0/+0；Mul16有效。返回tag严格等于本请求的context.tag XOR loanSequence，error/status先于数据使用；此tag只在当前单outstanding租约中校验，不是跨命令防重放。
- 本批不新增 local clear/abort 控制口。loan.abort 和 resetLoan 恒为 false；错误回复因此可保持 valid 并被 waitLoan 退休。绝不把 resetRequired 反馈为高保持的 abort/resetLoan 后等待被抑制的 terminal。
- 任一失败 held done；done.fire后 owner locked，只有协调全局复位能恢复。共享 loan 若处于 held error，须先在抑制信号低时退休，进入 lLocked；若外部使用原 resetLoan，仍须 lLocked、DDR drained、无DDR poison。协调全局 reset 同时覆盖 memory/scalar/loan，不能只 reset owner。此owner不实现全局排空器。
- 单 memory OR scalar OR loan outstanding。request不fire不占用；read成功不记writeBytes；只有匹配成功write ACK才记64B和推进。错tag优先于error，部分私有写不回滚。transport必须把零延迟response持有至wait.ready，不声称同边沿收发。

## 原序与资源

- 新增 gates[63] 读恢复 final cumulative（读总数3681，显式比软件多1），随后 chunk Exp。
- 每row：gate→Exp(cum)→Add(finalCum,-cum)→Exp(rem)；每K/Q beat 读K→读Q→KB→KBG→QG→KE全部成功，然后KB/KBG/QG/KE逐次写ACK。V逐beat读→VB→写ACK。pair因果lane逐项earlier gate→Add→Exp，整beat写；上三角+0但不算，对角仍算。
- payload恰4×512bit=256B：A=K、B=Q、C=KB、D=KBG；QG覆B，KE覆A；写C/D/B/A。V/VB/pair复用A。gate只保必要scalar words。另有context、scalar words、索引/计数/状态，不能将256B说成owner总面积。
- full64rows，包括M16 padding scratch行；无新input padding读、无external output/state写。
- 成功计数：2209 Exp、2144 Add、2560 Mul请求及成功结果各齐；3681读、2816写ACK=180224B；phase2 receipt output/state=0。状态时间只内部cycles计数，不把理论服务槽当硬件实测。
- 最终done背压时包括cycles、计数、receipt、decay身份/value在内所有字段保持；done.fire前不得新job，失败之后不得再入。原共享服务代码/顶层和既有源均保持只读。
