# v7：仅文件/输出树上限后继（尚未执行）

v6实际96.0453秒工具exit1；真实lower HW/SV和export准备完成，写出时File too large。原file48MiB硬限/64MiB树采样限保持触发记录，输出SV由工具失败清理掉，无完整SV/hash。OUTPUT_BASIS.json绑定receipt3e688d58…/log6e99c135…；不是时间不足或AS上限失败。观察leader VmHWM约1030MiB，依然不是整树峰值。

仅提高单生成文件硬限48→128MiB，输出树软采样64→256MiB；SV checker的字节上限及actual native_limits检查同步固定。总180/工具150秒、CPU1、AS2GiB、parent log2MiB、其他全部输入/优化/verbose/采样/资源结构门原样保持。128MiB不是已测最终大小或保证成功；是基于真实>48MiB写失败的一次有界扩大，若仍触门先诊断不自动追加。文件总量仍受256MiB采样约束，非整树文件硬配额。

## 官方split-verilog选项检查
固定官方firtool.cpp:184-186提供split-verilog每模块一个文件并以-o指定目录；442-446走populateExportSplitVerilog。它可以分散单文件大小，但需要新的多文件闭包/duplicate/interface/top检查和filelist，未知个别模块是否仍超48MiB。当前最窄路线保持单文件格式，未切换split或改变硬件/优化；不混入新checker语义。

与v6相比，只有run_sv/owned_compile/check_sv/test_cold内对应数字、此文档/OUTPUT_BASIS/manifest变动；strict_cleanup、leader采样、IR/schema/工具和官方源码完全不变。8+8+5+5冷测。

候选命令（需root单次GO）：
python -B production_silu_feedback_sv_output_plan_v7_20261017/run_sv.py --ir production_silu_feedback_structure_attempt_v2_20261017/structure/ProductionQk16KernelBench.fir --receipt production_silu_feedback_structure_attempt_v2_20261017/receipt.json --firtool production_qkv_native_tools_v10_20261017/firtool --out production_silu_feedback_sv_output_attempt_v7_20261017 --execute

只真实firtool→SV，无Java/providerlink/lint/nativebuild/动态数值。原每次失败独立保留；新生成若成功仍须接口库存与独审，不算完整block PASS。
