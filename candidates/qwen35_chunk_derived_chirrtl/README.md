# DerivedAndPair：单 owner CHIRRTL 前端限定结果

本增量包公开一份实际使用的 emitter、两份监督入口、纯 parser 控制、相对补丁和小型复现元数据。不重复生产 owner、旧模型、完整工具 pins，不含机器计划或运行载荷。

## 已完成

29组纯 class-log parser 控制自然通过。之后两阶段真实 JVM 自然退出0：先只编译新 emitter，再构造一次枚举绑定修复后的 GdnChunkDerivedAndPairOwner 并调用 emitCHIRRTL。495个冻结输入含身份 stamps 前后相同，142个旧class与3个新emitter class保持各自身份。

生成一份213402字节CHIRRTL（不是SystemVerilog），仅一个circuit和一个owner module，无子实例、extmodule或memory实例。117个实际绑定端口的宽度与方向通过，并由独立静态IR解析逐叶核对：60输入2525 bit、57输出2790 bit，包含clock/reset。外层Flipped Loan接口方向也已核对。

实际候选加载集合严格为24个原接口/常量/owner类加3个emitter类，655个隐藏Lambda均来自18个精确已加载宿主。编译产物中虽有Loan、MemoryEngine、HardFloat等实现定义，这次没有加载这些服务实现或在IR中实例化它们。子JVM锁定guard记录外部exec、network、guard替换尝试均为0；此范围是原Java调用路径，不宣称通用系统沙箱。

两阶段均由原WNOWAIT监督确认自然0、身份锚定、reap、进程组消失与cleanup。原监督在观察自然退出后仍执行确权进程组清理信号，不声称“从未发信号”。总180秒、共享工作150秒、编译120/展开30秒上限以及5秒cleanup/25秒post保持；详见SUMMARY.json。

## 文件及复现边界

7份源码或补丁都是冻结原字节。补丁基于此前LoadPrep前端源；INPUT_DELTA.json引用已公开Derived R2的349输入复现表哈希，仅追加142个class、3份来源元数据与1份emitter的相对内容pins，总495项。87 JAR和314工具未重复制或下载，生产源码不重新编译。

本包是非独立可运行摘录。launch_chirrtl.py仍绑定原私有FROZEN_PLAN内容哈希；机器路径计划、原类文件与权限/执行记录未包含。不能直接运行本包launcher、替换pins绕过校验，或把摘要当新执行权限。新环境需先重建并审定完整本地绑定。

## 尚未证明

CHIRRTL是硬件中间表示，是真实前端展开结果，但不是硬件握手/数值仿真。没有Memory ACK/背压运行测试、真实Scalar/Loan运算、完整chunk或Host接线，也没有firtool、SystemVerilog、RTL仿真、综合、时序或利用率结论。原编译失败、旧前端失败和Qwen2执行/清理UNKNOWN均保留。

包内不含原日志、原收据、CHIRRTL载荷、工具二进制、JAR/class、权重、数组或机器路径。parser中的固定临时路径是纯合成字符串fixture，不是实际输出路径。
