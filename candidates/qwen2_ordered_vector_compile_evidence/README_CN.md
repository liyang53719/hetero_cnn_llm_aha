# 独立 class-compile 证据增量

本片关联候选提交 `5a8e99c8db278bbb5e441d4fdc294c20dbf41f00` 的 ordered_fold.patch（SHA256 `e2325b7d7436a269687ba9fe1d2aaa45ef9a8b109189b2fa815e28aea7e998b8`）。原16文件及其“当时 compile TEMP”记录保持不动；这里是后来独立执行的新证据，不追认、覆盖旧PASS/TEMP，不混入其他canonical修复。

## 已证实结果

一次有界 `scala.tools.nsc.Main` 编译自然exit0，80.608秒，92份Scala产生550个class，共9,588,880字节。其中89份baseline源码逐字不变，只替换候选的Qwen2Block、QwenOwnerProtocol、HostBlockTop三份postimage。未复用旧class目录；classpath只有已pin的87个JAR。选择完整92源闭包而不是拿旧class只编3文件，是为了避免构造器参数变化后混用旧调用方ABI；“只改3源”不等于“只编译3源”。

独立审查重算所有源码/class哈希与receipt一致，三个SourceFile属性分别对应10/12/32个生成类；4个目标顶层class哈希列在 SUMMARY.json。输入/工具前后不变，清理确认完成，error=null，compiler log为空。

资格仅 PASS_SCALA_CLASS_COMPILE_ONLY。没有执行Chisel硬件构造、构造期require、elaboration、emitter、RTL、数值、同拍协议、M128或利用率/时序验证。编译器会检查构造器源码类型，但不运行enable=true的硬件实例。不能把class文件存在说成目标电路已实现或频率已达标。

源码及工具均已有本地完整副本，无下载或重建。314项工具的前后SHA均一致，其中87个JAR、179个JDK条目、48个系统库；这是保守历史工具身份集合，不是“实际加载的最小依赖”证明。TOOL_IDENTITY.json使用可替换逻辑根，不包含作者私有绝对路径。未提交class/JAR二进制、原始大日志或私有运行路径。

## 资源和失败边界

原compile_only.py / owned_compile.py / strict_cleanup.py字节未改。新source manifest和新RUNNER_PINS仅属于此次隔离运行，不改历史清单。

- 执行阶段总120秒；work截至108秒；cleanup截至116秒；剩余时间作postcheck。
- 单CPU affinity；JVM heap 1GiB；继承每进程虚拟地址空间硬限4GiB、每进程CPU硬限120秒。不是RSS硬限，也不是整个进程树总内存硬限。
- 日志2MiB硬限、单文件48MiB硬限、class树64MiB采样软限。
- cleanup按原直属leader身份及process-group锚点，两次完整absence扫描后reap；不使用宽泛pkill，不重置截止时间。
- 本次仅一次真实编译，无失败后隐藏重跑。早先其他任务的失败/临时记录不变。
- 不以shell exit0单独判定成功：旧驱动即使scalac失败仍可能外层exit0。必须同时读取receipt并要求 status=PASS_SCALA_CLASS_COMPILE_ONLY、scala_class_compile_pass=true、exit_code=0、cleanup_complete=true、error=null、inputs_reverified=true。

## 可执行复现步骤：不自动下载、不自动运行下一阶段

需要精确main候选、现成87-JAR cache、匹配JDK21、原20份HardFloat源码。若任何pin不符，停止；不要放松pins或临时联网补依赖。以下目录变量须为使用者自己的路径，其中NEW、BASE92、PATCH3、STAGED、COMPILE_OUT均不得预先存在：

    ROOT=...                       # 含5a8e99c候选和本证据增量的checkout
    EVIDENCE="$ROOT/candidates/qwen2_ordered_vector_compile_evidence"
    CLASSCOMPILE="$ROOT/candidates/qwen2_resident_matrix/production_qk16_rebase/classcompile"
    NEW=...                        # 新source recipe输出
    BASE92=...                     # 新baseline完整92源
    PATCH3=...                     # 新候选三文件overlay
    STAGED=...                     # 新当前92源及原runner副本
    COMPILE_OUT=...                # 新编译证据目录
    HARD_FLOAT_SCALA=...           # 原20文件所在目录
    DEPENDENCY_CACHE=...           # Maven相对路径对应DEPENDENCY_PINS.json
    JAVA=...                       # 已pin JDK的bin/java

1. 调用公开source-only recipe（故意INCOMPLETE/exit2，不是失败自动改成功）：

    python -I -B "$ROOT/candidates/qwen2_composed_handoff/replay_handoff.py" --source-root "$ROOT" --output "$NEW" > composition.json

保留原exit2和完整report，仅当 bounded_slice=PASS_EXISTING_COMPOSITION_AND_RETAINED_QK_CONTROL_MODEL 且五个postimage pins匹配时继续。该命令自行限制单CPU/20CPU秒/256MiB；不运行Scala/native/RTL。报告本身继续INCOMPLETE。

2. 使用原source-only builder生成baseline 92源，再应用本片三源补丁：

    python -B "$CLASSCOMPILE/reproduce_sources.py" --production-source "$NEW/production/source" --qk16-source "$NEW/donor" --hardfloat-scala "$HARD_FLOAT_SCALA" --output "$BASE92"
    python -I -B "$ROOT/candidates/qwen2_ordered_vector_chisel/prepare.py" --selected-root "$NEW/installed" --out "$PATCH3"
    python -I -B "$EVIDENCE/stage_inputs.py" --repo-root "$ROOT" --baseline-root "$BASE92" --candidate-overlay "$PATCH3" --out "$STAGED"

stage_inputs只检查/复制92源和三份原runner代码到新目录，不启动Java。原PLANNED_SOURCE_PINS仍检查baseline；本增量SOURCE_PINS检查替换三份后的92源。

3. 独立preflight，不启动Java。原runner需要其自身目录在Python import路径，所以使用正常 `-B`入口；不要裸加`-I`导致import owned_compile失败：

    python -B "$STAGED/runner/compile_only.py" --preflight-only --source-root "$STAGED/scala" --dependency-cache "$DEPENDENCY_CACHE" --java "$JAVA" --output "$COMPILE_OUT"

4. 确认无其他编译冲突后，执行一次有界class-only。下面继承与本次相同的AS/CPU上限，原runner内部限制affinity/heap/deadline；不能附加runMain或emitter：

    (ulimit -v 4194304; ulimit -t 120; python -B "$STAGED/runner/compile_only.py" --execute-approved-once --source-root "$STAGED/scala" --dependency-cache "$DEPENDENCY_CACHE" --java "$JAVA" --output "$COMPILE_OUT")

实际已执行JVM命令在COMMAND_TEMPLATE.json中逐参数保留，仅替换机器相关路径根。本次额外使用独立-I bootstrap，核验owned_compile导入来源后调用完全相同的runner；没有修改旧runner。上述正常-B入口是原runner公开支持的等价编译入口，不能把未来复现当已经执行第二次编译。

5. 检查完整receipt全部成功条件、inputs前后哈希、550类清单、输出没有.v/.sv/.fir/.mlir以及cleanup proof；保留任何失败，不自动重试。构建产物数或时间不同需要记录，不修改原证据掩盖差异。

## 远端CI与剩余验证

已核查相关4个Chisel workflow：offline-workspace、continuous-prefill、p0-safety、qwen2-continuous-block，均无可直接选择“本片精确92源、只class compile、不emit/test”的路径。p0-safety虽有独立compile step，但后续仍emit/test且项目不对；不能据此dispatch整个工作流。本次没有新增/dispatch远端CI。

原 production_source_identity.py 存在compile子命令，但未绑定本片92源与上述监督约束，不替代本次runner。最小真实行为验证安排见 BEHAVIOR_PLAN_CN.md，仍需后续独立授权范围及新证据。
