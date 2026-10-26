# Runtime GDN phase2/3/4：源码与编译通过，实际 CPU240 FAIL（TEMP）

本批新增 3 个实现与 1 个测试 Spec，固定 max32 接口、runtime16/32、5-bit head、1-bit chunk；不改变完整4096 MAC要求，不实例化新增算术或32份数据服务。原 owner 和旧 FAIL 保留。来源增量可在把 BASE_PINS 的两个旧 owner 复制到新路径后应用 SOURCE_DELTA.patch；新 Layout/Spec 为完整原字节。

源码独审限定地址/容量、上下文/布局绑定和原状态尾部逐字保持。随后真正 fresh Scala compile 36 源、174 classes 通过；编译 Spec 不是执行其4个 case。实际4-case尝试触发原 CPU240 门，0/4 完整 PASS、0 个 case terminal；这不是数值或完整行为通过。该失败已由独立 actual 审确认；审计完整性 PASS 不升级目标 FAIL。AUTHOR_FAILURE_SUMMARY 是独审前原字节历史摘要，原 pending 字段保留，当前结论以 ACTUAL_FAILURE_REVIEW_PROJECTION 及绑定独审为准。

phase2 要求精确 phase1 context/layout/tag/generation/head/chunk/ACK/count，phase3/4 要求完整 phase2 和相应计数/decay。它们只比较值，不认证私有 scheduler 真的执行过 producer。prepared Q/K 已按 value-head 展开，consumer 直接索引，不能再次 head//2。每 head 状态/双chunk scratch 是外部分配，不等同片上32份容量。

原测试计划每个叶 DUT runtime16→32→16、选 head15/31/15、chunks0/1/1，不 reset；但本轮没有完整 case 结果，不能把计划或静态80517周期当实际进度/吞吐/完成率。mock Exp 返回1、loan 返回0，只是协议替身，不证明 HardFloat/Vector 数值；有限bit转置 case 同样未完成。实际无 job/row 进度记录，不能断言死锁、具体热点、功能错误或真实已执行周期。

错误保持 outstanding/锁定，需父级共同排空/复位；tag32||每job序号32不是epoch，无超时watchdog。phase3局部成功收据不能替代整个phase4或全局DDR drain。全head coordinator、phases5–17、全块/完整4096五profile通用top接入、RTL数值和MAC利用率仍未验。

复现见 SOURCE_PINS/REPRODUCTION；仅角色化argv与原监督器hash，不是原绝对路径launcher、完整动态闭包或运行GO。单独恢复20 HardFloat源、106官方依赖；禁止自动重试/升预算。新环境记录不回填旧phase1缺失的JAVA_*快照。原 snapshot check_contract.py 路径依赖问题明确保留，不作为可直接运行的新工具上传。

不含真实模型输入/权重、NPZ、classes/JAR、low FIRRTL、原日志或运行缓存。后继观测/性能候选不纳入此版本。

原 RESULT 完全没有 exit_code 键（不是显式 null）；独立 cleanup direct wait 为 -9。三个完整扫描中后两个为空屏障；采样CPU240.08不是最终精确CPU总量，RSS196849664B不是连续峰值，elapsed242.98692909500096是内部监督时间，不冒外层总wall。原硬限与cleanup可能竞态，不能仅由 -9 指定最终信号来源。56+12实际前后flight在Java前后且Python已运行，689验证循环不是逐项独立hash轨迹；无原日志进度不推出零clock或具体卡点。
