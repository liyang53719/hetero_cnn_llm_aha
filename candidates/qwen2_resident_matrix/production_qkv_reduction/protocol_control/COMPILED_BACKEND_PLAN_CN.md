# 同一控制 harness 的编译后端方案（仅只读计划）

## 当前工具盘点
PATH中没有 verilator、iverilog、firtool；workspace/tmp/opt及常见cache未发现其可执行文件或已pin归档。已有 g++/gcc/make/perl/JDK；未运行工具版本命令或安装新工具。存在firtool-resolver jar不等于已安装firtool。

已观察二进制SHA256（本机identity，不冒称vendor下载pin）：
- x86_64-linux-gnu-g++-14：6b3696e4dcb85e1c949c732a02befa50e3983ecf94ce7e8e58d9d503b954b79d
- x86_64-linux-gnu-gcc-14：a23ecab8ff08f09ad8c80602c2c5df7f49e09c25905cb8975902e101bf72635f
- make：8a229baf64671988cfb5af43ba3070c6ce7214cf32bcf96155115559d1466fa7
- perl：b85210f03baeb859ee20b1324e59497f27f319eda9e2d3d1ecd163a79d884a7d
- JDK binary/release见 JDK_PINS.json。

## 既有固定来源与wrapper
仓库 `candidates/qwen2_public21_binding/run_control.py:26–30` 已固定：
- llvm-firtool1.62.1 linux-x64 jar SHA63acdcb58ed12d4c1aa0ecdedc6e2425a252e94eefb75df9253c118d7d222039
- Debian verilator5.032-1+b2 amd64 deb SHA238ab4ca84cddd371f113cd549f16f2d65c43e7b4962a763bea1d259158dd3b2
- sbt-launch1.10.2 SHAcdd6963b622f42690cb2e3154bde3f3257a03839f216e1b5d7420000d6a71817

`scripts/setup_hetero_chisel_loan_toolchain.sh` 包含官方Maven/Debian URL、安全解包和verilator wrapper。它还会取sbt/git/其他依赖并运行版本命令，不能为了本门原样全跑。已有 run_control.py 的600秒run_group先wait/reap后killpg，不满足新严格保留leader证明，不能原样复用。应只复用固定工具来源/路径约定，继续本门严格cleanup。

已pin chiseltest6.0.0 jar常量池显示 VerilatorSimulator 调用 Compiler.lowFirrtlToSystemVerilog、runVerilator、compileSimulation/make；Compiler有sverilog路径。因此本计划明确会产生控制 SystemVerilog、Verilator C++与可加载本地仿真库。不能声称仍是CHIRRTL-only。独立结构门仍emitCHIRRTL。是否需要外部firtool以实际所选backend命令和依赖审查为准，不因resolver jar就自动下载/执行。

## 最小改动
保持生产91-source、harness、fixture、全部断言/脚本数据/markers不变。测试Spec仅把TreadleBackendAnnotation换成VerilatorBackendAnnotation并形成新固定SHA，不宣称Spec字节完全不变。无Host缩减、无fake arithmetic、无绕过lowering、无新生产顶层。

编译后端只验证同一7模块控制设计；仍非完整block RTL，仍没有真实 Dense/Matrix/SFU/iDMA 或生产kernel五债务。小router解释器分门虽可作排障，不能与Host分门通过合并称集成通过。

## 待批准的预算草案
不沿用Treadle20秒startup限制去限制native编译。建议新绝对总stop250秒：预检10，Scala compile60，原CHIRRTL结构20，backend lowering+Verilator+C++ build120，真实callback后30，cleanup预留10；各阶段都取原stop剩余时间，不续时。

Java heap1GiB/ActiveProcessorCount1；native make严格-j1，Verilator threads1；必须审实际argv/Makefile，不能只设可能被-j覆盖的MAKEFLAGS便声称单并发。每个生成文件8MiB、父日志2MiB，不自动扩容。原CHIRRTL<=2MiB/指定7module/无memory/extmodule/FPU门保持。native compiler总RSS尚无测量；执行前需明确可用进程级/cgroup内存约束，不把Java-Xmx当整机RAM限额。

所有新工具只在获准后隔离下载/解包并核既有归档pin与执行二进制hash。当前没有下载/安装授权或执行GO；此预算仅方案，不是运行承诺或性能估计。
