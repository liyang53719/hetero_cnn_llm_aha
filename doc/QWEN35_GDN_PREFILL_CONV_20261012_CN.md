# 0.8B L0：投影实际写回到 Conv4/SiLU 与 history staging

这是前缀数值模型的第二个实现增量。完整 GDN block、真正 chunk64×2、公共 Command128、Chisel/RTL 及状态提交仍未完成。

## 接线与数值合同

同一输入从固定 checkpoint embedding 开始，顺序执行 typed RMS、真实共享 Matrix 的 QKV/Z/AB、Conv4/SiLU。Conv 的输入只能是同一 TypedMemory 中前级已写入、ACK、接受完成的 QKV 区域。全部目标最初为哨兵，以真实地址识别，未注入参考中间结果。RMS 和 Conv 共享同一 Scalar 对象；原 Matrix、五个 accumulator bank 和 Dense 模式保持原实现。

每个32-channel组仅保留四tap权重、raw history、当前输入与输出。四次乘法显式使用原 op6，FP32 ascending Add；Conv 后先 BF16 RNE，沿原 degree7 ExpNegative/Div/legacy Mul 计算 SiLU，再 BF16 RNE。原非有限值、公共运算异常和负 Conv≤−80 的未支持域保持拒绝。没有用 NumPy exp 或第二个 SFU 执行实际链。

Conv output 与 channel-major raw history 分别真正写回并等待所有ACK。接受成功terminal后只发布激活，history始终保持 staging，generation不前进，等待未来完整block的双状态fence。两个输入窗口分别使用内部零历史；第二窗口 token128..255 不是 carried GDN 状态验收。

pre-SiLU 节点通过默认关闭的只读callback观察；只传不可变坐标和BF16位，返回值不参与计算。记录内存是外部诊断数据，不计为owner SRAM。有无观察的小测试比较输出、请求调度和Scalar调用均相同。

## 验收与限制

[紧凑回执](../reports/execution/QWEN35_GDN_PREFILL_CONV_20261012/RESULT.json)绑定同源实际输出、固定参考及原生参考。对照在全部实际终态与输出封存之后才运行：

1. 实际 Conv、SiLU、raw history 对独立全数组分节点FP32配方逐bit比较。
2. 实际 Conv/SiLU 对相同实际QKV输入下的固定官方函数，分别保留原≤1 BF16 ULP门。
3. 实际末SiLU对原官方RMS/独立原形状QKV再Conv的完整前缀参考，保留max≤0.03125、mean≤0.005。此前12项投影/RMS门也全部独立保留。

官方参考执行固定 revision 的原 causal_conv1d_fn AST、fullshape BF16 Conv及SiLU；Torch2.10 CPU default、1线程，输入窗口形状没有缩小。这个运行器尚不是完整官方DecoderLayer/cache调用。原始bit差和±0数值等价分别报告，不把0 ULP写成逐bit相等。

M16 两窗口78.61秒，M128两窗口253.76秒，均完成10个owner终态。M128最高RSS457,764KiB，成功ACK共7,979,008B，其中98,304B为仍未发布的history staging。实际Conv/SiLU/history对固定配方全bitexact；同输入官方Conv/SiLU均0数值ULP，两个窗口分别919/925处raw bit差全部是±0。纯官方前缀对照的SiLU最大绝对误差分别0.001953125/0.0078125，均值约1.83e-8/1.41e-8，原门通过；其逐元素ULP诊断仍保留，接近零处可有很大的ULP数，不据此另换原绝对误差门。

29项源及ELF/fixture在执行前后保持一致；先完整封存actual，再运行比较。RMS原fixed期望只有预绑定SHA，随后以同源配方补物化四个小文件并核SHA完全等于原summary；这一后处理没有重跑actual链或改原回执。软件tick、Scalar请求、C++ FMA和CPU壁钟不是硬件cycle。4096 MAC/cycle 固定资源分母不变，当前完整GDN周期和MAC利用率仍为空，不沿用Qwen2旧映射上界。

## 小门与下一步

本地71项合成测试及新冷源码checkout的完整workflow顺序通过。新增覆盖实际RMS→Matrix N64→跨两个group的Conv、两span最后ACK、错误/abort/reset排空、尚未接受的success遇abort禁止发布、原错误status保留、已接受success不能被迟到abort撤销、源/输入丢失仍输出FAILED回执。

CI只重复这些小软件门与一次小C++库构建，不下载权重、不重跑实际M128、不生成RTL。固定源码和调用方依赖由新构建receipt绑定；未使用历史work里的隐式库。后续只读source-trigger修改保持job步骤完全一致。

下一步把实际Conv/AB写回接入M128输入准备，再做真正chunk64×2的FP32 Q/K/状态数据流；不将128次M1递推冒充chunk，也不把FP32状态降成BF16以适配现有Matrix入口。随后接gated norm、O/residual、postNorm与FFN、完整双状态fence，最后公开Host程序及Chisel/RTL。S02/S04/Q35B/U00.2/U01和五block M128总门保持开放。
