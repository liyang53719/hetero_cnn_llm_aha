# 复现边界与 source-only 检查

## 不执行目标的检查

1. 以 `pins/NEW_SOURCE_PINS.json` 检查四 Scala、两个 Python 和结构期待 JSON 的 bytes/SHA256；四 Scala 为实际编译原字节。结构文件为实际 r2 checker/test/期待原字节。
2. 在新空临时目录复制 `source/Qwen2Block.scala` 为 `Qwen2Block.scala`，运行 `git apply -R -p1` 指向本目录 `probe/score_write_probe.patch`，逆变换结果 SHA256 必须等于 `probe/PROVENANCE.json` 的 baseline_sha256。此操作仅复制/补丁，不导入或编译 Scala；原 source 不修改。正向补丁应精确恢复。
3. 在本目录的 `structure` 子目录运行 `python -B test_check_chirrtl.py` 及 `python -B -O test_check_chirrtl.py`：各21个小合成结构用例，不读取真实 FIR、不启动 JVM。合成通过只验证 checker 拒绝门，不是电路仿真。

## 已有 baseline 与新四源

`pins/BASELINE_REFERENCES.json` 绑定现有公开 `candidates/qwen2_ordered_vector_compile_evidence` 的 README、92-source pins、stage_inputs、工具/依赖/runner pins，并直接绑定 unchanged PackedAttentionStreamClient。旧公开 README 记录有界 source-only recipe 和原92源编译方法；它的 source recipe 有意保留 `INCOMPLETE/exit2`，不能盲改为通过。

92 源中60份可直接匹配当前 main blob；另32份来自已发布补丁/recipe或外部 HardFloat 源，**本片不声称92份均为可直接取回的repo文件**。使用既有完整 baseline 时必须逐一满足92-source pins以及 `RETAINED_CLASS_PINS.json` 的550 class hash。需要重建 baseline 的使用者应遵循旧公开recipe，准备其精确20份外部HardFloat输入与固定工具；新生成class不自动视为历史同字节/同资格，也不据此继承旧授权。

本次四源增量编译确实复用已审550类；没有重新编译92源。新20类 manifest仅保留身份/来源元数据，不发布classes。不存在 PackedAttentionStreamClient override。不要在整个源树或JAR目录使用通配符。

## 需要独立授权/监督的实际阶段

`pins/OFFICIAL_DEPENDENCY_PINS.json` 给官方 Maven 坐标/URL、顺序、bytes/SHA256，106项显式闭包（含编译器、Chisel插件及预备测试依赖）；不自动下载或执行。JDK21及历史工具身份复用已有 `TOOL_IDENTITY.json`，其314历史工具条目不是运行最小加载集合。

`pins/EXECUTION_ROLE_PROJECTIONS.json` 的两个 argv 数组是原真实 receipt 的逐参数路径角色替换：`${JAVA}`、`${DEPENDENCY_CACHE}`、`${SOURCE}`、`${BASELINE_CLASSES}`、`${NEW_CLASSES}`/`${STAGED_CLASSES}`、`${COMPILE_RUN}`/`${CHIRRTL_RUN}`。原 receipt hash保留原始数组身份。它们不是可直接运行的私有config或新授权，也不提供原 supervisor 的路径/进程控制能力。

复现者必须先验证 pins、无冲突任务、全新输出目录及外层 CPU/AS/RSS/wall/log/output 限制与受锚定清理；替换角色后应另行审查。实际先只编译四源，检查exit/cleanup/20类来源及全部pins；之后另行准入 `OrderedQkBehaviorElaborate 1`，使用本片结构期待检查。不能自动串联 ordered-off、ScalaTest、Treadle、M1、SV 或仿真，不能失败后盲目重试/扩大预算。

本包省略私有 supervisor 的硬编码环境实现，只保留原源码/manifest hash与资源/参数投影，因此**不是一个完整可直接启动的私有运行环境快照**。范围只到本次实际编译和 selected-on CHIRRTL；源中未来测试入口存在不等于已经执行或数值通过。
