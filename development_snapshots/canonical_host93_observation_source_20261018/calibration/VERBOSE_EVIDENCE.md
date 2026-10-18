# Fixed Scala2.13.16 verbose observation contract

All sources were read from scala/scala at fixed tag v2.13.16. OFFICIAL_SOURCE_PINS.json records their official Git blob identities. No compiler source or package was run to obtain this evidence.

1. StandardScalaSettings defines -verbose as a Boolean with the --verbose alias and no post-set hook. It has no debug/deoptimization hook. ScalaSettings separately defines -Vdebug/-Ydebug with enableDebugAndDeoptimize; statistics collection also has a cold-statistics/deoptimization hook. Neither is enabled in this candidate.

2. SymbolTable.informProgress is gated on verbose and forwards through inform. Reporting.inform calls reporter.echo. The default reporter setting is ConsoleReporter; its constructors use autoflush PrintWriters. PrintReporter.echoMessage also explicitly flushes after each printed informational message. Thus these messages do not wait for compiler completion to leave the Java writer buffer. This is not an fsync guarantee and cannot guarantee a line if the process is killed before its call finishes.

3. SyntaxAnalyzer emits a parsing-progress event before parsing a compilation unit. SymbolLoaders wraps source/class/package completion in informingProgress; that helper emits elapsed-message text in a finally block. A loaded-event message therefore proves the wrapper was reached and exited, not necessarily that loading succeeded or the compiler phase completed. Later error text must be considered.

4. Global's uniform end-of-phase informTime is gated by areStatisticsEnabled; verbose alone does not enable that setting. Debug phase-start messages also require debug. Therefore -verbose is NOT a guaranteed every-phase timeline. Its useful evidence is the concrete parsing/loading/progress events actually seen. With no later message, the precise phase can remain unknown.

5. Output includes classpath setup, parsing units, and source/class/package loading; it scales with loaded symbols and paths. The fixed93 input count does not give a proven log-byte cap. There is no static proof it remains under2 MiB. Each flush has I/O/timing cost, so this run is an observed calibration, not an uncontaminated reproduction of the earlier silent run. The existing2 MiB acceptance/48 MiB per-file hard limits remain unchanged and no budget is extended by logging.

Relevant fixed sources:
- https://github.com/scala/scala/blob/v2.13.16/src/compiler/scala/tools/nsc/settings/StandardScalaSettings.scala
- https://github.com/scala/scala/blob/v2.13.16/src/reflect/scala/reflect/internal/SymbolTable.scala (informProgress/informingProgress, lines80-85)
- https://github.com/scala/scala/blob/v2.13.16/src/reflect/scala/reflect/internal/Reporting.scala (inform/echo)
- https://github.com/scala/scala/blob/v2.13.16/src/compiler/scala/tools/nsc/reporters/ConsoleReporter.scala
- https://github.com/scala/scala/blob/v2.13.16/src/compiler/scala/tools/nsc/reporters/PrintReporter.scala (printMessage/echoMessage)
- https://github.com/scala/scala/blob/v2.13.16/src/compiler/scala/tools/nsc/ast/parser/SyntaxAnalyzer.scala (line102)
- https://github.com/scala/scala/blob/v2.13.16/src/compiler/scala/tools/nsc/symtab/SymbolLoaders.scala (completion wrapper, line248)
- https://github.com/scala/scala/blob/v2.13.16/src/compiler/scala/tools/nsc/Global.scala (lines1555-1570)
- https://github.com/scala/scala/blob/v2.13.16/src/compiler/scala/tools/nsc/settings/ScalaSettings.scala (reporter default and debug/statistics hooks)
