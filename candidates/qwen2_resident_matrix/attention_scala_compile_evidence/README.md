# Packed client / Raw scratch：Scala 类文件编译证据

## 已完成
- 首次真实编译：17 个源文件，6.810446 秒，退出 1，清理完成。缺少原有 MatrixAccumulatorSeedController；随后四条类型推导错误保留在原始日志哈希中。
- 修正闭包：只加入原始完整 controller，先前 17 个 Scala 文件字节不变。18 个文件在 14.483935 秒编译成功，编译器/外层退出均为 0，清理完成，生成 129 个 `.class`。
- 两次尝试及调用者记录分别保留。没有类文件、JAR、模型权重或张量随本目录发布。
- 冷检查验证源重建、87 个依赖哈希、原始收据与类文件哈希；独立审查已完成，原件支持的 4+4 冷检查通过（零跳过）；源码、129 个类文件哈希与 87 个 JAR 哈希均已复核。

## 明确边界
这只证明 Scala 类型与接口闭包可编译。没有运行构造器/elaboration、ChiselStage、CHIRRTL、SystemVerilog、仿真或数值任务。没有证明 default-off 的两种硬件展开、完整 owner 集成、面积或性能。

## 精确源构造
prepare.compose(destination, original_root=...) 不执行编译器。
1. 复用 raw_kv_parent.prepare_unit 的 13 个原始/声明切片源。
2. 用 attention_raw_scratch 的三个已固定父模块替换对应源。
3. 加入 attention_packed_stream 的 MatrixPipeline 和 PackedAttentionStreamClient。
4. 从原有 seed 修补后的 RetainedMatrix 提取完整 RetainedMatrixEndpoint / RetainedMatrixClockGate；从固定 WideMatrix 提取 WideMatrixStep / WideMatrixResult，使用与实际执行完全相同的头文本。
5. 加入完整原有 MatrixAccumulatorSeedController。其四个项目级 Seed 类型已在 MatrixAccumulatorSeedProtocol 中；禁止占位类。
6. 最终 18 个 SHA256 必须等于 EVIDENCE.json 的实际成功源图。
original_root 指含完整原始源码的 checkout。WideMatrix/controller 的内容哈希固定；不要求复制历史私有工作目录。

## 依赖与命令
使用仓库 chisel/rope_hardware_oracle/maven-lock.json 固定的官方 https://repo.maven.apache.org/maven2/ 内容。选择全部 .jar，排除 Scala 2.12 与 org/scala-sbt，共 87 个；逐个核验锁哈希。prepare.dependencies 只核验本地缓存，不下载或安装。
Scala 2.13.16、Chisel/plugin 6.7.0、Java 21.0.12.1；Java 二进制与 release 文件哈希见证据。prepare.command 仅返回原始命令结构：
java -Xmx1024m -XX:ActiveProcessorCount=1 -cp CLASSPATH scala.tools.nsc.Main -classpath CLASSPATH -Xplugin:PLUGIN -language:reflectiveCalls -d CLASSES [18源文件]
1 GiB 是堆上限，不是 RSS 上限；ActiveProcessorCount=1 是 JVM 调度提示，不是 OS CPU 绑定。

## 有界执行与审计
executed_launcher.txt 是成功执行的原始 launcher 文本，其 SHA256 在证据中固定，仅作源码审计。它使用固定 supervisor/producer 的信号保护、同 PID exec 清除继承 signal mask、环境白名单、子进程组清理及源/依赖后检。ATTEMPT.json 是不可变的非终态起始标记；summary.json 是终态。后检/最终化失败不得留下成功收据。
实际调用必须由外层 `timeout --signal=TERM --kill-after=10s 50s PYTHON launch.py --execute` 包围，最多 60 秒包括前置准备和清理；调用者另外记录外层退出。内部 work 最大 50 秒。该文本的机器路径/历史 PLAN 和 FILEMAP 哈希不能直接当成另一环境已经执行过的配置；迁移时须建立新的已核验工作目录与输入清单，并独立审查/授权执行。此包只重建源与命令，不自动执行 Java。

## 冷检查
从仓库根目录：
PACKED_COMPILE_ORIGINALS=/path/to/original-evidence-root python -m unittest candidates.qwen2_resident_matrix.attention_scala_compile_evidence.test_evidence -v
再用 python -O 运行同一模块。外部原始证据不存在时，两个原件/类文件/缓存检查明确跳过，不能宣称原件复核通过。

## 后续
- 待办：分别展开默认/启用参数分支，验证真实硬件接口；需要独立批准的最小 elaboration 任务。
- 待办：实际 owner 调度、bank 端口、panel 资源与错误排空集成。
- 当前不启动以上任务，也不改变任何已冻结数值运行输入。
