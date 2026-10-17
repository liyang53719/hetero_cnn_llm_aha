# 固定四段 FMA SystemVerilog 组件发射方案（未执行）

范围：直接emit既有 gemmini.HeteroBF16FmaPre/Mul/Post/Round 四个RawModule；不新建替代硬件顶层、不实例化Host、Matrix array或作业。新Scala App仅是软件发射入口。每组件一份SV文件，内部HardFloat子模块定义另计；禁止跨文件同名重复定义，不能用生成文本拼贴或静默重命名绕过。无仿真、数值或完整block验收。

## 输入与端口链

固定92源/550class基准仍为QK16 classcompile receipt cf84b0dac54e5d1b6efe5646621e84ca4c92f4863e7a88fcb082068206352ec3，复用字节与逐类SourceFile。新增ProductionFmaComponents.scala后93源，预期只编App三类得到553；所有550不得变化，依赖jar不得shadow。87原jar/JDK前后复验。源码 EmitHeteroBF16Fma.scala 和20个HardFloat源码均在完整source pins中。

Pre输入a/b16、c32；输出mulAddA/B24、mulAddC48、meta54。Mul输入24/24/48，输出49。Post输入meta54/result49，输出raw41/invalid1。Round输入41/1，输出FP32out32/flags5。四段名称与matrix lane5 u_pre/u_mul/u_post/u_round及其实际本地logic位宽逐项核对。既有Pre/Post源码require元数据54/raw41；RNE、tininess_afterRounding保持原源码。没有附加流水级或寄存器bank。

消费端为已pin seed-enabled bf16_context_fma_pipeline_lane5_rev8b_b_candidate.sv，SHA见TOOL_PINS。此门只核provider端口与消费lane绑定，不证明整个12SV Matrix+iDMA provider闭包。

## 工具与真实生成格式

Chisel6.7.0 / Scala2.13.16 / JDK21 均复用原pins。固定官方firtool1.62.1 binary SHA7f52d2a3782d09736895f66e7eb0e5cc4b3b1b18aa1ad0d04fca4cd6e42cd2ee，来自官方Maven llvm-firtool1.62.1-linux-x64.jar SHA63acdcb58ed12d4c1aa0ecdedc6e2425a252e94eefb75df9253c118d7d222039，已本地提取，不动态下载。Chisel jar内FirtoolBinaryPath选项确认接受--firtool-binary-path，因此显式指向专用wrapper，不走自动工具解析。

真正会生成4份SystemVerilog：HeteroBF16FmaPre.sv、Mul.sv、Post.sv、Round.sv。firtoolOpts固定--preserve-values=all、-disable-all-randomization；wrapper原样保留stdout/stderr，用独立64KiB argv侧文件，不重复此前stdout污染错误。wrapper核ELFhash，实际单CPU、native每进程RLIMIT_AS2GiB。Python3 interpreter也pin。禁止Verilator/GCC/EDA或RTL仿真。

## 原总90秒有界运行

同一90秒绝对stop；入口预检≤10、classcompile≤20、四段合计emit≤60，不是每组件60。cleanup预留5秒，各阶段继承同一stop。Java-Xmx1GiB与CPU affinity1；这不是整树内存硬限。生成每文件8MiB硬限，四SV各8MiB后验；父log2MiB，输出树64MiB采样软限。每SV定义≤32、总定义≤64为未知实测规模的保护；超限保留失败，不盲增、不改硬件凑门。严格原owned cleanup helper SHA30458e67...，absence barrier后才reap。

checker核四文件、精确根模块/端口方向和位宽、无重复module定义、消费lane端口全覆盖和本地位宽；拒未知端口语法。没有声称这替代lint、链接或算术验证。原发射器生成结果未知；本轮仅源码/合成文本冷测试。

## 待审核的命令

    python -B run_components.py --source-root "$SOURCE92" --base-classes "$BASE550" --cache "$CACHE87" --java "$PINNED_JAVA" --firtool "$PINNED_FIRTOOL" --matrix-lane "$PINNED_MATRIX_LANE" --out "$FRESH_OUTPUT" --execute

源码ROOT/类根由已发布production_qk16_rebase/classcompile的便携入口重建。当前本地已知输入为prefill_production_qk16_compile_plan_20261017/source及attempt_01/classes；firtool为production_qkv_native_tools_v10_20261017/firtool，消费lane为production freeze内对应SV。全部显式参数，运行仍需独立审查及root单次GO。本轮不运行任何Java/firtool。

冷测试6normal+6-O，另静态对实际消费lane的位宽/绑定核对；synthetic SV不是工具生成物。预算/环境/cleanup实现沿已独审v3，生成文件上限由48MiB收紧为8MiB；原550+3类/完整93源及工具配置前后核验。
