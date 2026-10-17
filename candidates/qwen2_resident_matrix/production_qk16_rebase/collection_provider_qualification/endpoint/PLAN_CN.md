# 原 Matrix endpoint 分层 lint 诊断门，未执行

完整Bench B2在AS4GiB分配失败，原receipt保留。本门是单个真实原endpoint组件资格，不能替代完整8endpoint/4096MAC Bench链接。

选定原 qwen2_matrix_command_endpoint 顶层，显式 -GENABLE_ACCUMULATOR_SEED=1'b1（单个原样argv，无shell）。其原阵列32cluster×16lane=512，五context与原四FMA完整保留，不能缩lane/cluster。原12个Matrix源+原tc_clk+同一共同SV=14文件；只取组件需要的定义文件，不改任何SV。共同SV仍69MB且包含全部Bench定义，但验收top为endpoint。未知依赖若因完整共同SV中未选中模块出现诊断，先保留，不bbox。

四FMA消费共同SV中原名称，避免旧Round冲突。所有选中源hash保持；1052原闭包pins仍全部前后核，另pin官方Verilator文档。组件文件不需iDMA include；原4TARGET宏保留。省略iDMA文件属于组件边界，不能据此宣称完整Bench缺模块已关闭。

显式官方 --timescale 1ns/1ps 作为缺省timeunit/timeprecision，与现Matrix显式1ns/1ps一致；不使用timescale-override、不压警告。官方已pin exe_verilator.html:2126-2130说明该选项仅补未定义单位模块。此为输入编译单位设置，需review/root接受；不是按位置waiver。源门依旧默认warning fatal，无-Wno-fatal/-Wno。后续其它warning须按位置/值域审查，禁止全局忽略。

沿B2原210total/180tool/10cleanup、CPU1/AS4GiB/file16MiB/log2MiB/tree64MiB采样softcap、leader4096采样。当前仍解析大共同SV，单endpoint展开耗时/内存未知，不承诺通过。严格ownedcleanup及输入postflight保持。修旧stage摘要generated_file_limit_bytes为真实16MiB，原FAIL回执不改。

命令（待独审/root单次GO）：
python -B production_qk16_endpoint_lint_plan_v2_20261017/run_lint.py --workspace /workspace/scratch/f28987e955ed --out production_qk16_endpoint_lint_attempt_v2_20261017 --execute

不build/sim/数值。通过也只说明固定512lane单endpoint的本次lint，完整Bench需随后独立资源与警告闭合门。

v2唯一功能delta：参数常量由无尺寸1改为1bit二进制1'b1。原v1实际运行39.764秒exit1，仅该32→1位warning触发fatal；原receipt bd8a003e1246c217a2d6759e3bacef56bef804b8c424ecaac1bcf08aed0fb842保留。后继不改源码/预算/timescale/警告设置，未执行。
