# Python候选参考接真实Qwen2 Host（TEMP）

旧bench的C++ forward仅诊断且有整块重复计算。本候选删除所有Dense/RMS/Attention/SiLU等C++前向运算，改为加载独立Python全21执行的20个物化输出；内部score/prob依原Host不额外外写。20输出共5,636,096 FP32 words，名字/顺序/字数与原OUTPUTS表逐项检查。原真实4096 MAC和Qwen2 FP32存储不变。

prepare.py逐项核已保存RESULT进度SHA256，冻结输出副本与编译期字数/指纹；本地数据不提交。运行必须设置PYTHON_REFERENCE_DIR，无C++回退。loader只取得oracle引用，不接触DUT mem/initialized；先完整核大小/指纹再写参考数组。trig复用同份冻结cos+sin输入，核尺寸与指纹，不重新计算。仅trig是DUT输入，参考输出不是。

普通和DNDEBUG加载器实数据测试通过，覆盖全部20输出、错误指纹不变更目标、错误字数拒绝、边界哨兵以及冻结trig。静态检查已删除C++forward。仅供数/参考加载测试，不是Host仿真或数值PASS。真实接口C++编译另由Host闭包任务核实。

Python结果仍CANDIDATE_REFERENCE：Matrix flags NOT_QUALIFIED、Dense未全部输出Fraction对照。完整五块硬件仍0/5；原head4 underflow FAIL保留。没有执行任何长RTL数值仿真。
