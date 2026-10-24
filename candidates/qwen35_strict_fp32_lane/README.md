# Strict FP32 单 lane 隔离源码原型

一个新 full32 Pre，复用原 Mul/Post/Round 各一个。Strict 模式两次完整RNE，Mul失败不进入Add，成功才提出accCommit；BF16模式仅原单FMA的raw result/flags。原BF16配置、公共M1/Host、4096主阵列与16Vector均未修改，本包没有任何集成入口。

当前文件是待root独立小控的源码，不继承以前编译/CHIRRTL/Python资格。只拟运行 tests.py：源码literal检查、20个数学定向例、256个固定种子finite triples，以及signed zero、subnormal、溢出、编码/NaN/Inf拒绝、injected Round故障、held/reset/阶段模型。软件整数significand模型与独立Fraction邻值参考不共享decode/round函数，不使用Python float作为oracle。

这仍不是执行Scala或HardFloat，不是真握手/RTL数值；注入的BF16 NaN/Inf raw响应只测协议传播，不证明原NaN payload。模型只对应原型功能状态，不对组合逻辑延迟/面积/Fmax作预测。

重要已知集成阻断：HardFloat与旧vector16.cpp在minnormal边缘的UF判据不同，见FLAGS_BOUNDARY_ADDENDUM.md。root已选本prototype保原HardFloat规范；不能用软件参考PASS声称旧GDN fatal30合同全等或未来集成通过。

固定依赖见INPUT_PINS.json：原四份接口/数值源码，加已有HardFloat小源码闭包。没有工具JAR、class或权重复制。原脚本外层必须落实10s总墙钟、1CPU、CPU10/10、AS256MiB；TEST_COMMAND仅提案不授权。作者没有执行测试、候选、JVM、native或RTL。
