# NoCSE normal_m1：原 CPU600 预算下仍 FAIL

**实际状态为 `FAIL_NORMAL_M1_TREADLE_RETAINED`，没有完成测试 case，也没有行为或性能 PASS。** 此独立新运行未给旧运行加时，未重编 Spec/硬件，未发送诊断 SIGQUIT；原 CPU600、原 CPU150、NoCSE CPU150 的 FAIL，以及既有单源编译/CHIRRTL/软件 M128 有限范围结论均保留。

## 已发生的实际结果

| 项目 | 独立审查绑定的实测 |
|---|---|
| sampled / final aggregate CPU | 600.0100445639999 / 600.516278779 s |
| 外层 wall / timeout / root return | 600.8715823919629 s / false / 1 |
| normal exit 字段 / cleanup direct reap | null / -9，不能混写 |
| sampled RSS 高水位 | 1,251,176,448 B；不是连续峰值或 cgroup 隔离证明 |
| 运行与静态身份 | 1,266 runtime pins，6 inventories，原 17 + NoCSE 新 3 = 20 类 / 670,791 B |
| 保留日志 | 15 行；7 条 origin、4 条 W005；0 READY、OBS、CASE_PASS、ScalaTest 成功、线程 dump |
| 审查 | 10,557 项身份检查、49 项小日志/终态检查；24 artifacts / 59,625,776 B，另有 6 项 root records |

保存的清理证据在原 leader/group 与已观察身份范围完成，末两次确认 barrier；不是本包新作活进程观察。原输入和产物身份未变。隐含 classpath 槽的 pre/post/review 端点不存在，不等于连续 loader 隔离。7 条 origin 不含 Spec/MemoryReply 的独立 runtime CodeSource；两个 MemoryReply 即使字节同旧类仍按已审新来源选择。

## 不能从失败推出什么

- **本次 CPU600 没有线程采样。** 旧 NoCSE CPU150 的约 120 s SymbolTable 栈不能外推为本次 600 s 热点、最终停止位置或整段 profile。NoCSE 的加速、命中次数和优化因果收益仍未证明。
- 无 READY/OBS 不证明 framework reset 零 clock；body 与 framework clock 数均未知。正常 case 尚未完成，也没有独立完整行为结果。
- 旧原 CPU600 与本次可见日志在仅归一运行根后相同，是有限可见日志身份，不是内部执行轨迹相同或相同热点的证明。
- 初始 LOW IR 仍为 58,897,360 B，SHA-256 `71a27f80112970011761ffe361e6466a57a53f4eae95a816a252bc162ec4ea56`。仅物化初始文本字节一致；不证明 PrepareAst 后 graph/node/edge 大小、后续状态或完整语义相同。本包不重新读取或解析大 IR，也不重复解析实际日志。
- 不宣称数值、完整 block/full29、M128 RTL、有效 MAC 周期利用率、系统 duty 或用户 90% 硬件目标通过。

## 最小来源与资源范围

通过 `pins/EXISTING_PUBLIC_REFERENCES.json` 精确复用已发布的 checker、NoCSE 59 B Spec delta、类与官方依赖链；**不复制原 checker/Spec/JAR/classes**。既有公开 `BEHAVIOR_EXPECTATION.json` 是先前路径角色化的合成 fixture，不是本次私有 runtime expectation；原运行期 expectation 仅按 hash/长度绑定。

正常 M1 supervisor 从原 CPU600 版本仅改变 schema/`validate_manifest` 身份准入，其余 17 个定义逐字不变；原资源/cleanup/staging/checker 调用与成功资格未放宽。仍为 1 CPU，600 CPU / 720 work / 750 total / 780 outer，heap 1 GiB、stack 4 MiB、AS 4 GiB、sampled RSS 2 GiB、单文件 192 MiB、输出树 256 MiB；没有 SIGQUIT/pidfd 诊断路径、预算扩大或自动重试。源准备文件中的 TEMP/未授权字样是历史阶段，不改写成执行许可；实际结论来自单独冻结的最终审查。

本批仅去私有路径的原审查投影、来源/角色 pins、必要摘要和中文计划。原始输入、权重、IR、raw log/dump、进程身份、private argv/config、classes/JAR 均不上传。包装只校验小型元数据、已有引用、源字节差分和合成负控，未运行 DUT/JVM/native/reference 或信号。

主任务继续 **ongoing**。冻结的只读路线摘要见 `evidence/READ_ONLY_BACKEND_ROUTE.json`：已有 LOW IR 不等于可恢复的 backend/graph 缓存；原 ChiselTest Verilator 路径仍经过 Scala SV lowering。下一步优先准备另审的独立 firtool SV emission-only 门，而不是继续给 Treadle 加时；缓存工具/版本头的源码依据不等于当前 Core 已通过解析、生成或运行兼容。端口、memory/reset、assertions、实例闭包与后续同刺激接入仍需实际独审。

这些只读计划不构成新 PASS。本包不含未执行 SV 候选、资源提案、运行配置、适配器或 GO，不上传工具，也不把别的设计旧 SV 当当前 Core 复用。
