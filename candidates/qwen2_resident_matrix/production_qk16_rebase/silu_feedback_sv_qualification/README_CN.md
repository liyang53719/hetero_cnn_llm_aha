# 修复后真实 SV 生成与独立离线库存检查点

真实firtool已生成完整69,464,271B SV，SHA93fe8475…，工具exit0/96.222秒。原整体v7仍失败：自定义checker误把同名类型/实例名当两次实例。新离线checker仅跳过已经完整解析的instance span，独立8+8及同一实际SV重放通过。49定义、目标Bench子树8endpoint/8clock/1iDMA的受限直接实例库存和named-port通过；未真实provider链接、未数值。

SAFE_HISTORY.json清晰保留原真实组合环FAIL、两次60秒超时（其中诊断确认环检查Done43.284秒）、48MiB写出失败、128MiB成功生成但库存误拒、新离线通过。原receipt从不改成PASS。投影仅保留hash/相对cleanup/采样统计，不携带PID/boot/session/proof身份。没有上传69MB SV/39MB IR/classes/jars/权重。

## 可复核入口
python -B test_cold.py
python -O -B test_cold.py
python -B verify_existing_sv.py --sv "$EXACT_GENERATED_SV"
最后一个入口需消费者已有同hash实际SV，30秒只读验证；若没有历史输出，仍可运行冷测，但不得声称重放了实际SV证据。

## 源码与生成链
1. 从已发布 production_qk16_rebase/classcompile/README_PORTABLE_CN.md 的生产/QK donor/HardFloat公开链重建92源。
2. 使用相邻 silu_feedback_fix/reproduce_sources.py 单表达式修复并 --include-bench 生成94源；本包只添加 ProductionQk16KernelStructure.scala，SOURCE95_PINS逐项固定全95源。原修复后557实际类可用相邻compat入口验证；若自行完整重编94源，必须另设有界资格及源码/依赖/SourceFile后验，不能把新class字节当原历史字节。
3. 原A使用固定JDK21/Chisel6.7.0/Scala2.13.16和106依赖（相邻fix包pins），只编独立App后发射CHIRRTL；选selected=true/capacity1024/no-job，原90秒/48MiB/768定义。此包提供原emitter和源pin，但不伪称重新构造A的完整launcher已在公共环境实跑。
4. generation_v7/ 是实际执行B1的原冻结源码和pins，包括官方tag来源、owned cleanup、leader统计及180/150、CPU1/AS2GiB/file128MiB/log2MiB/tree256MiB上限。其run_sv.py接受显式 --ir --receipt --firtool --out --execute；INPUT_PINS固定历史A IR及receipt，不允许随便更换。完整重建产生新receipt时须另建受审候选绑定新身份，不能直接改冻结pins。
5. 官方firtool1.62.1来源/下载固定脚本可复用已发布 production_qkv_reduction/fma_components 的便携工具recipe；这里不重复工具包、不自动下载或执行。

原generation_v7 checker仍有历史误拒，必须保留以重现原失败。根目录check_sv.py是独立修复后checker；两阶段不能混称一次原运行PASS。可用上面的verify_existing_sv独立复核同一SV。原完整输入、95源/560类/106jar/JDK/工具/IR/argv/limits已本地独立前后复核；安全摘要不包含它们的机器进程原证据。

## 当前链接阻点
原312provider的独立FMA Round与本SV有两个同名Round helper，接口和内容不同（FMA版本io_infiniteExc常量化并去端口）。禁止选择一份覆盖或手改生成SV。正在审原HostBlockCollection式同一Chisel命名空间共同发射Bench+四FMA；B2验收top仍Bench，容器不是替代目标。后续共同新资产另批，不覆盖本历史69MB输出。动态必须消费同一资产，不能用Chiseltest独立再发射来假装已复用闭包。
