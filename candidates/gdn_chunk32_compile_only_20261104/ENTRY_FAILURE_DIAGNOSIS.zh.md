# Retry1 入口失败与 R6 修复

固定失败身份：run 41778903739 / job 126405659780，source 046a1096ab7deb60bea6d8c2b274c0cf3326bafb，activation ee7f7b9a93fea191593a8baf519662a44513cd36。原 job 不重跑。

独审以固定 source Git tree 对齐全部 198 路径（172 Scala、所有 local/repo tool pins 与 workflow），196 项一致，恰两项共享工具与过时 compatibility 副本不同。SOURCE046A_REMOTE_CLOSURE.json 仅含仓库相对路径、mode、bytes、Git blob/SHA256，无本地路径。ACTUAL046A_TOOL_DRIFT.json 保留两个旧/实际 digest。

真实 source046a 的原 compile_only.main 在纯回放（只模拟 git HEAD、截停 supervisor）确定抛出 repository tool source drift；首个冲突是 restore_model_inputs.py，未进入 JDK/native。原日志本身仍仅 ValueError；确定门禁来自固定源码与真实字节回放，不假称旧日志已经含 path。

选择最小修复：不改共享工具，仅更新当前 candidate 的 TOOL_PINS 与 wrapper 固定 MODEL_RESTORE_SHA256。已逐段审远端实际 diff：restore 只更新内嵌 gate pin 和 CLI supply 选择；generation gate 的 supply 分支及 require_generation_binding 的 finite/profile 分支不在本次 legacy source_inputs 调用路径。保留 selected_inputs('legacy')、checked_paths、159 源门禁及原官方107 JAR检查；actual162独立选源不变。未把 GDN32 加到旧 generation 白名单。

新增入口安全诊断覆盖 ARGUMENTS、IDENTITY、SOURCE_CHECKOUT、OUTPUT_FRESHNESS、TOOL_PINS、SOURCE_SELECTION、ENVIRONMENT_POLICY、JDK/HOST、SOURCE_CLOSURE、DEPENDENCIES、JAR_VERIFICATION、SCALA_COMPILE。已知门禁只输出固定 reason；未知异常仅有限 class+phase，不输出异常消息/源代码/环境。tool pin失败只输出受限相对 label、role 与 expected/actual SHA256。所有原资源、pin、alias、cleanup门保持。

新 dormant launch identity：ci_launch/gdn32_compile_only_20261104_retry2.json，nonce gdn32_compile_only_20261104_retry2。workflow、副本、validate_launch、compile_only 与 TOOL_PINS 一起更新。保留 once/retry1 历史文件；本包不含任何 launch JSON。父级独立发布源，再核 source parent/only-added/attempt1 的第二提交，不能重跑旧 run。硬件 generation 2b2f02d698f16a57ba696c52c4669a1226a68c5378efdc8ebe392cc1b9098f52 不变。

验证：29 CI validator +14 dependency +10真实入口 =53 tests，normal/-O，三个测试模块分别启动独立 Python 进程。不要在同一 unittest 进程合跑：dependency_fix 的全局拒绝 subprocess audit hook 会阻断入口模块获准的纯 Python verify-only 子进程；这是测试隔离要求，不是生产例外。入口测试使用已核198目标的 source046a fixture，原main失败、修后main到首个supervisor被截停；Python fetch wrapper --verify-only真实子进程验证完整source_closure+helper159+actual162，无下载/无compiler。测试在独立 publication fixture 内按 MERGE 覆写后，从实际候选路径执行，workflow 与副本一致。只有历史原155五冲突回归使用明确 GDN32_LEGACY_BASE；其余闭包/入口基于固定远端198目标。此证明不能排除后续真实host/JDK/下载/compiler资源失败。

本次没有 native Scala编译、Top展开、EDA、DUT、数值结果、CI激活、网络写入或binary上传。硬件 fault terminal仍仅条件性，未匹配债务隔离，不声称全局有界终止或97358通过。
