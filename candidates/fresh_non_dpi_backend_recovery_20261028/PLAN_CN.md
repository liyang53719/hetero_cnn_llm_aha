# TEMP：新统一硬件的真实仿真后端恢复

从 fresh 155 源、860 class 完整编译和原始 Host high 重新构建。旧 16-lane 或丢失环境证据不迁移。五块统一 4096 MAC / 32-lane、128-token 完整数值仍未通过。

本候选不再次 elaboration、不改硬件源码，只把已独立核验的 high/annotations 送入原有 FIRRTL 仿真后端。原有 FIFO 和 private denseAcc 的存储表示变换保留：FIFO 两项容量 262154 bit，denseAcc 16×256×32=131072 bit，原控制、原异步读时序、原三处整阵列写和 last-connect 顺序不变。此变换不是物理 SRAM 推断，也不是最终冻结 RTL。

完整旧 Core/FIFO AST 已缺失，不能宣称历史 AST 等价。当前完整 AST 由官方 parser 单独输出并人工/独立检查后固定新 hash。新 helper 类名避免覆盖原 901 class。高层有 8984 个 DontTouch，加一个 TargetDir；所有 annotation 保留，仅把 TargetDir 从 host-diagnostic 显式移到 compiled-host。新增 20 个 SiLU tap 也保留。

执行顺序：run_once.py compile、run_fma_r2.py fma、run_once.py host，每次必须传 --execute-approved-once。原 run_once.py fma 分支已确认因绝对 TargetDir 失败，不再使用；保留原失败记录。R2 仅改为相对 fma-library 参数和新输出目录，未改 Scala 源码、class 或算术。FMA 载体实例化原四个 HardFloat 算术阶段，绝非软件 DPI；Host 输出是 Chisel 数值测试所需的仿真后端 SV，尚需绑定全部物理 endpoint/iDMA、编译并用原始完整128刺激实跑，最后独立比较数值。任何发射成功都不意味着数值 PASS。

资源：一次仅一个 JVM，Host heap4GiB、AS10GiB、CPU600秒、wall660秒、单文件384MiB、输出树1GiB；RSS5GiB/输出树/日志是采样限制而非逃逸子进程硬隔离。没有 Verilator 或并行 Make 启动。

后续 fullDUT driver 保持原来完整 launch/DDR 表和真实握手：P0 使用新修复的原生 BF16 Dense 权重，Qwen2 其他 FP32 存储仍保留。驱动是单 outstanding、AR 后一拍开始 R、每周期一个64字节 beat、W 收齐后下一拍 B 的合成功能内存服务，没有 LPDDR 时序模型。基于它的利用率只能标为该功能 bench 的结果，不能冒目标内存性能。


## 本轮实际结果

- 初始8helper类型编译：29.233秒，860旧class字节不变，生成901总class；随后官方parser单独检查37.429秒通过。
- 新3helper类型编译：54.320秒，901旧class字节不变，生成928总class。
- FMA R1：FAIL，4.136秒，绝对TargetDir被官方Compiler拒绝，未完成发射。R2仅修正相对路径，9.525秒实际发射通过。
- 原始Host仿真后端发射：399.056秒，进程峰值RSS 4,410,683,392字节。12个实际产物。SV 192,485,469字节，SHA256 5f9e60ab5993c4cc22b1dc2828d33080e62900a940817c4f400b57007b770dd6。
- 92个SV模块定义，展开1056实例，8个512-MAC物理端点接口、8个时钟门控、1个真实iDMA接口。85端口（41入44出），launch844位，两路512位AXI数据。共享bank有32个ALU；wholeTop为81个ALU和17个BlockScalarFloat，不能描述为全芯片仅一组浮点单元。
- 保留8984个DontTouch，唯一annotation改动是TargetDir。18个被转换的仿真存储表示不等于全Top只有18个存储节点：最终AST共927个DefMemory节点，包含原始bank等。该数量不是物理SRAM宏或端口签核。
- FMA库150095字节，SHA256 09e714962628ea2460e03df1d75872976578d2af34a3ec76da0703cd884e62ac。只有原始四阶段库的发射资格，尚未数值验证共享HardFloat/provider整体连接。

只通过上述编译、解析和发射范围。五块M128完整Chisel数值仍0/5，最终冻结RTL数值仍0/5，MAC利用率无本轮实测。下一步绑定已恢复真实物理provider并进入同一DUT的全128执行与独立比较，不改成单token循环或叶子测试。
