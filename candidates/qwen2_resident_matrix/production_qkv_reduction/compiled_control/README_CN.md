# 原 Host + QKV reduction 编译控制门，v15

实际一次有界运行 PASS_CONTROL_ONLY，47.577秒。固定7模块：Record128Reader、TypedTensorReader、HostBlockCommands、DenseTileSumBridge、DenseBlockReductionCoordinator、Public21QkvReductionRouter、测试harness。原Host真实命令解析、router/coordinator握手实际进入Verilator callback；正常M16脚本18,457拍、1正常+7故障场景通过。系统生成1,560,217字节控制SystemVerilog，SHA256 603e165b5f61df8af356616c6f5196e4906e4ce52ec74346160fb181ae8a169a。

边界：共享服务响应由脚本驱动，无真实Matrix/SFU/iDMA算术；不覆盖QwenOwnerKernel真实五类物理债务。没有M128完整block数值PASS或利用率测量，不能宣称用户全目标完成。原Attention约48.2%理想上界仍只作功能候选，SFU约81.95%上界也待优化；目标90%未改变。

## 证据与历史

CONTROL_PASS_PROJECTION.json是原receipt安全投影，保留原SHA、555类hash、阶段时间及相对cleanup顺序；不是原receipt原字节。不含PID/boot/session/宿主时间、绝对工作路径、raw日志/IR/classes。

v7：2MiB文件限额截断lowered FIRRTL。v8/v9：Treadle callback预算不足，v9已推进至少64拍。v11：单CPU完整94源编译60秒超时。v12：wrapper marker污染Verilator版本stdout。v13：GCC PCH触发8MiB文件限额。所有这些失败仍成立。v15用官方VM_PARALLEL_BUILDS=0单TU，保持8MiB/单CPU/AS2GiB/原预算，无PCH文件，未改DUT/生成RTL/断言。

## 重新构建545类，不依赖私人cache

本目录记为C；父候选目录P提供已发布的replay.py及compile/prepare_sources.py、compile_only.py。CHECKOUT必须满足所有固定源hash；未匹配不能刷新pin。先按父README replay得到WORK/source。

下载入口只下载固定官方文件并验hash，不安装、不运行；需要显式--download：

    python -B "$C/download_pinned.py" --kind jars --out "$JAR_CACHE" --download
    python -B "$C/download_pinned.py" --kind tools --out "$ARCHIVES" --download
    python -B "$C/download_pinned.py" --kind hardfloat --out "$HF_ARCHIVE" --download

HardFloat官方commit c1105e6ac6a0dd90fc80893efc4830ab609005d3；tar SHA固定在下载器。提取后HARDFLOAT_SCALA指其hardfloat/src/main/scala目录。准备JDK21，其java及release须精确匹配JDK_PINS；本包不提供安装器，不能静默换JDK。Linux系统make/perl/GCC14等须满足NATIVE_TOOL_PINS。

    python -B "$P/compile/prepare_sources.py" --source-root "$WORK/source" --hardfloat-root "$HARDFLOAT_SCALA" --out "$SOURCE91"
    python -B "$P/compile/compile_only.py" --preflight-only --source-root "$SOURCE91" --cache "$JAR_CACHE" --java "$JAVA" --output "$BASE_OUTPUT"

批准后去掉--preflight-only才重建生产545类。此过程是独立classcompile，不是控制测试；父入口有原88秒预算，不是本次250秒的一部分。BASE_OUTPUT/classes必须完整匹配BASELINE_CLASS_PINS，不能以任意缓存替代。原545由87jar编译；新测试106jar，共同81同hash、移除6、增加25，明确分开的classpath，不将下载目录全部jar并入。

## 准备真实metadata与工具

    python -B "$C/prepare_tools.py" --archives "$ARCHIVES" --out "$TOOLS" --pins "$OBSERVED_TOOL_PINS"
    python -B "$C/prepare_run.py" --source-root "$CHECKOUT" --out "$RUN_SOURCE"

prepare_tools仅静态提取，运行时仍以包内NATIVE_TOOL_PINS核完整工具文件清单；OBSERVED_TOOL_PINS不能替换包内pin。prepare_run用固定发布generator真实生成6个command/descriptor表，核原10文件hash；源码包没有bin或其base64编码。无权重/数值模型运行。

## 有界控制门

下列命令会生成控制CHIRRTL/FIRRTL/SystemVerilog/C++并运行控制仿真，需要单独执行批准：

    python -B "$RUN_SOURCE/run_protocol.py" --source-root "$SOURCE91" --cache "$JAR_CACHE" --java "$JAVA" --tools "$TOOLS" --base-classes "$BASE_OUTPUT/classes" --out "$FRESH_CONTROL_OUTPUT" --execute

完整94源固定，只复制原545类后重编3个测试源；原545不得改变，新10类SourceFile限三源，runtime唯一classes目录，无旧Spec/shadow。总250秒，同一个stop；compile60、backend startup120、callback30及cleanup保留。Java heap1GiB；native每进程AS2GiB、实际-j1、单CPU、VM_PARALLEL_BUILDS=0。不是整树内存硬限。CHIRRTL2MiB/7模块无memory/extmodule/FPU；生成每文件8MiB硬限，父log2MiB；128MiB输出树是采样软限，可能超冲。任何失败保留证据，不自动重跑或扩预算。

纯源码检查：python -B test_portable.py；python -O -B test_portable.py。这些冷测不运行工具或硬件。本便携包仅做冷验证及metadata重放；实际PASS来自固定v15运行，操作源码字节相同。
