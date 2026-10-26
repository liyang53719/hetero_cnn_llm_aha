# 完整 4096 基线：Yosys 原生前端实际失败记录

**本次目标为 FAIL，不是综合 PASS，也不能据此判定硬件不可综合。** 输入是原 OrderedQkRealMatrixCore 完整 8×512 基线及非 DPI providers，不是已完成统一五 profile top。一次官方 Yosys0.52 原生执行 exit1，在读取第一个 `inputs/common.sv:2652` 时遇到 `unexpected OP_CAST`。已定位到 BlockScalarFloat 的 packed-array assignment-pattern token `'{`；尚未选择/检查 top，没有进入 hierarchy/proc/check，未产出 stat.json 或 design.json。configured8/4096 是准入字段，不是本轮 graph 实测结果。

另一个独立失败是冻结输出门拒绝 `home/.local`（空 history 所在父目录）；不是删除该门或抹除原结果。原输入、脚本与资源上限未改，无重试。cleanup 完整，native exit1；清理阶段对原组的 SIGKILL 记录不等于资源超限 kill，leader 当时已经终态。

## 证据层级
- 459 原源/输入/runtime pins 前后 PASS，**不等于 staged 副本末端全 hash**：输出门异常发生在 `stage_inputs(post)` 之前，该字段缺失。
- 独审对 15 个小 staged provider/script 重算 SHA；48,274,540 B common 只核当下 size/mode 及前 371,489 B/2,654 行与原件一致，未独立重算完整 staged-after SHA。包作者不再读实际 RTL/二进制。
- 记录 sampled owned-group RSS355,414,016 B，sampled group+parent CPU1.541420108 s、最终 parent+waited-child CPU1.702478607 s、outer wall1.877101451 s。不是完整进程树 CPU 积分、连续真实峰值或全机/并发合计峰值；未触及资源上限。
- root CPU1 / 原 cold CPU0 是一次获准的有限并发例外与源绑定；逻辑 CPU 区别不证明物理核/缓存/内存带宽隔离。没有 live cold RSS 或联合硬限证明。未修改/暂停 cold。外层 timeout 分支本次未走，不扩张为其完整资格证明。

## 源与历史
原0712为源 STOP/未执行；r2只补显式 `--execute-approved-once`、拒绝 normalized cell-type key collision，并迁移身份，原工具/15RTL/script/caps不变。此前资源 FAIL、4W005/1SV warning以及本次两失败均保留。

本包提供原字节 Yosys script、两 literal 角色化监督源码模板、原函数逐字提取的小 stat parser 与合成控制、官方工具与15RTL hash。模板不是可直接运行的 launcher/私有 manifest/新 GO。合成 parser 能数到4096不能冒本次真实硬件验收。原 restore_package.py 只供复现来源，发布/包审不执行下载或native。未纳未执行的 disallowPackedArrays 后继。

没有完整4096 hierarchy/proc/check、五profile统一硬件、数值、SV行为、技术映射、综合面积/时序/PPA或有效MAC利用率通过。早先独立的 Scala/CHIRRTL/SV 生成证据不因本次前端失败被抹除。
