# QK 单key owner路由：完整项目 Scala 编译证据

## 已完成
- 冻结的默认关闭 attention_qk_owner_route 补丁，通过真实完整项目类型编译。
- 83个完整Scala源（63项目源 +20固定HardFloat源），生成474个class文件。
- 实际耗时28.262122秒，编译器与外层退出均为0，清理完成；编译日志为空。
- 源/JAR/Java/监督器前后身份检查通过；保留调用者单独观察的外层退出记录。
- 当前目录独立审查已完成：原件核验4+4项通过、零跳过；原始QK六文件与执行输入保持冻结。

## 结论范围
仅 class-only 类型/接口闭包通过。没有调用Emitter main、ChiselStage、构造顶层、elaboration、CHIRRTL、SV、RTL或数值任务；没有实际展开默认/启用两种参数，也没有证明时序、硬件面积或性能。源码中保留原始Emit*.scala定义只为完整项目闭包，编译它们不等于执行它们。

## 可重建源
prepare.compose(destination, original_root=..., hardfloat_root=...) 仅写出固定源码：
- 原有49 continuous、9 p0、2 Gemmini、2 Seed，共62完整文件。
- 精确应用已审查stream与QK owner路由生成文件，并增加PackedAttentionStreamClient，形成63项目文件。
- 加固定HardFloat20文件，最终83源SHA必须逐字等于真实执行源图。
没有ABI占位类、裁剪声明或第二数组。original_root须包含对应原始完整项目文件；不要求使用历史私有目录路径。

HardFloat固定官方commit c1105e6ac6a0dd90fc80893efc4830ab609005d3；原有archive SHA55f9c47f73c5a0ff347ff0ff4fc72b6966ffaa6b6d29998a00b3956dce512de7。全部20源码哈希来自仓库历史hardfloat.sha256.json，与原有compile_inputs记录一致。此次恢复5.614043秒，仅从官方upstream读取并核验，未执行依赖源码。包内仅记录哈希，不发布HardFloat archive。

## 编译器 / 预算
原有87JAR lock未变；Scala2.13.16、Chisel/plugin6.7.0、Java21.0.12.1。prepare.command核验Java/release、87个JAR、83源码，返回scala.tools.nsc.Main命令，不运行它。
真实命令采用-Xmx1024m和-XX:ActiveProcessorCount=1；前者是heap上限，不是RSS，后者是JVM调度提示，不是CPU亲和限制。
强制外层 timeout --signal=TERM --kill-after=10s 90s PYTHON launch.py --execute，工作90秒，总100秒。executed_launcher.txt保留真实监督器源码供审计，包含初始ATTEMPT、信号保护子进程所有权、同PIDexec解除信号屏蔽、环境白名单、组清理、源后检与原子收据。
该历史launcher含原工作区布局/清单哈希；迁移环境必须生成新受审清单，不能把历史收据当成新执行。此包没有自动下载或执行入口。

历史59源编译28秒与其后独立emitter16秒仅用于运行前预算估算；先前18源编译14.484秒也不构成新环境完成保证。

## 验证
从仓库根目录执行：
PACKED_OWNER_COMPILE_ORIGINALS=/path/to/original-evidence-root python -m unittest candidates.qwen2_resident_matrix.attention_qk_owner_compile_evidence.test_evidence -v
再用python -O执行同一模块。提供原件时验证全部收据字节、474class哈希、83源重建和87依赖；没有原件时对应两项明确跳过，不能宣称原件验证完成。

## 待办
默认/启用分支真实展开与RTL闭环仍待独立审批和工程任务。raw scratch/PV6/16-key/完整prefill不在本次编译成功的集成声明中。
