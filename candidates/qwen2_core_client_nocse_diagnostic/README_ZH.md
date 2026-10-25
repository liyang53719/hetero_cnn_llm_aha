# NoCSE 单 Spec 编译与两样本 CPU150 失败诊断

**PASS 仅为一次真实单 Spec Scala 编译及其独立审查；实际诊断仍为 `FAIL_DIAGNOSTIC_RETAINED`（CPU150）。** 没有 READY、OBS、CASE_PASS 或 ScalaTest 成功；不是行为、数值、RTL、完整 block/full29 或硬件利用率通过。原 CPU600、原 CPU150、全部旧 FAIL/STOP 和既有 compile/CHIRRTL/软件 M128 有限范围结论不改写。

## 唯一源码变化与复现身份

- `source/OrderedQkBehaviorSpec.scala` 是已审原字节 16,760 B 新副本；第 33 行仅插入官方 `firrtl2.passes.NoCommonSubexpressionEliminationAnnotation`，精确增加 59 B。移除该唯一插入即恢复已公开原 Spec 的全部 16,701 B。`SPEC_ONLY.patch` 只把原私有路径头换成相对文件名，hunk 不变。
- 沿 `pins/EXISTING_PUBLIC_REFERENCES.json` 的确定 commit/blob/SHA-256 复用原 Spec、原四源/20 类、550 类、106 个官方依赖及原有复现源码链；不复制或上传 classes/JAR。其他硬件、PackedClient、probe、刺激、阈值与 clock 上限不变，原 probe 副本范围也不扩大。
- 实际编译仅此一个 Spec，产生 3 类共 131,576 B；编译 exit 0，aggregate CPU 11.574924921 s，外层 wall 11.657691419997718 s。独审验证注解构造字节与其余 179 个 code records 的符号化指令/操作数比较；不是只查常量池名字，也不是 JVM 形式等价或 runtime activation 证明。
- 诊断准确 stage **原 17 非 Spec 类 + 新 3 Spec 类 = 20 类 / 670,791 B**。两 MemoryReply 字节虽与旧类相同，来源仍须选新实际编译目录，不能用旧来源偷换。原 20 目录不在诊断 runtime classpath；原 550 类/PackedClient 不重编。编译/诊断角色与资源摘要见 `pins/SUPERVISION_ROLE_SUMMARY.json`；它不是可执行私有配置或新运行许可。

## 真实 CPU150 FAIL 与两份采样

| 项目 | 结果 |
|---|---|
| 预算终态 | sampled CPU 150.01972185 s；final aggregate CPU 150.49159626 s；root exit 1 |
| 外层 wall / timeout | 150.6548317069537 s / false |
| normal exit 字段 / cleanup reap | null / -9，二者不混写；保存的限定原进程组清理证明完整 |
| sampled RSS 高水位 | 1,201,958,912 B；不是连续真实峰值或 cgroup 隔离证明 |
| 约 60 s 窗口主线程 | PrepareAst / InferResets / InferTypes |
| 约 120 s 窗口主线程 | TreadleTester construction / ExecutionEngine.apply / SymbolTable dependencies |

独审 9,713 项身份检查与 103 项 dump 检查、1,319 runtime pins、24 artifacts 的闭环支持该**失败诊断证据**，不升级实际 FAIL。4 条 W005 保留。原 7 条 origin 日志没有 Spec/MemoryReply 的独立 CodeSource；未记录逐 pass annotation 对象或 CSE guard 命中次数。

原 CPU150 第二份主线程采样在 PrepareAst/CSE；本次第二份采样已在其后的 SymbolTable pass1。结合固定官方源码，这是该时点越过 PrepareAst 的阶段证据，不能量化速度、完成率、CSE 命中次数、整段 CPU 分配或因果优化收益。该时点尚未到后续 symbol table 完成、数据分配、表达式编译、初始 evaluate/framework 首次 reset；120 s 之后无第三份样本，不能据此宣称全程零 clock 或确定最终停止函数，也不能反推旧 CPU600 的唯一根因。

两次发送窗口不是精确 dump 捕获时间。保存的是共享 anchor、审过的 source gates、成功返回元数据及两份完整外观的线程文本；没有逐次原始 proc/pidfd 快照或 syscall trace，不构成独立逐次内核调用重放或一一送达确认。公开仅严格有序、去地址主线程 Java frame 子集，不是完整原 dump。

三次初始 `.lo.fir` 均为 58,897,360 B、SHA-256 `71a27f80112970011761ffe361e6466a57a53f4eae95a816a252bc162ec4ea56`；这是 PrepareAst 前物化文本的字节身份，**不证明后续 prepared graph、node/edge 数量或运行图大小相同**。本包不重新读取、解析或上传 IR。NoCSE 可影响初始 lowering 与 PrepareAst 中被排程的 CSE，但仍有 runTransform remapping，不可把整个 transform 说成绝对 no-op，也不跳过其他必需检查。

## 安全发布与后续状态

原报告/冻结仅以角色、长度、hash 绑定；投影明确去除私有路径、CPU placement 与进程身份。原始输入、权重、参考/事件数据、JAR/classes/IR、原 dump、private argv/config 不在包内。包装阶段只做原字节/可逆 patch、类选择 metadata、投影/隐私检查和微型合成负控，没有 JVM/DUT/native/reference 或信号重跑。

下一步仍是 **ongoing** 的精确范围验证准备；没有把整体任务置 done。本包不包含下一 CPU600 候选、配置、GO、未执行结果或上游 graph 算法/代数优化方案；不作加速、优化采纳或行为通过承诺。
