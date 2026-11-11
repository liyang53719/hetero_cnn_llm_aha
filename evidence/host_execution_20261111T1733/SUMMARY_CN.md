# 17:33 编译成本诊断与真实执行驱动（INCOMPLETE）

五块128 token完整原Chisel数值仍0/5，最终同刺激RTL未通过，4096完整block有效MAC80/90%未实测。原L0 head4 FAIL保持，不重启终态未知旧Qwen2/L3 Host。

## DONE：成本诊断和必要驱动
冻结LLVM602函数，HostBlockTopV4_eval单函数418006行/29.81MB；原llc默认-O2。还存在5612bit整数2131处、2348bit整数11399处，宽整数lowering可能是主因之一，不能仅归于优化级。原LLVM SHA f1542f319a2bd400034883e706efd7a0885f66d667adc280cb1fc70260eb27f0保持。
-O0先通过小型7边沿/reset、4strict打印/exit86、8192数组位序对照，然后对同LLVM新唯一23671做5GiB/240s有界llc。明确终态240.020s、exit124，object不合格，未链接，没有原样替代编译。小测试不迁移为Host资格。
真正Host联合driver已编码，比较完整1607520B Host状态及17输入/输出/rawflags，低相精确收敛上限64delta；低相冻结后一次Host高相并传播真实native边沿。新增每次eval sink freshness及singleton链接检查。新8周期reset/idle验证身份准备完成，无launch或profile恢复；因机器码尚未就绪，未运行。薄桥库SHA271b154d3256e5dded42d7706c258b5b75c75f56ef3795ab14b2e4b6e46118cb。驱动仅语法/接口编译通过，非实际联合时序PASS。

## Qwen2实际输入适配
复用1133真实输入与1433全21独立参考、1533准入，新增按请求只读取数、Wstrb字节写覆盖、未写先读拒绝及最终y完整覆盖后比较。实际原x分段读取及9负测通过，合成零输出明确比较失败；AXI单测覆盖ID/last、R/B背压和strobe。没有预装参考中间结果，没有重算参考或启动Host。
仍缺经校验的profile0命令/descriptor/地址绑定；恢复生成器只复制已丢原pin对象，未猜布局或冒metadata/trig映射完成。0.8B两块仍缺原hidden，35B两块完整payload仍缺，既有CDN拒绝未重试。

## ONGOING与下一步
找到官方arcilator --split-funcs-threshold，原命令未开启，默认没有分割；同版本源码确认该选项传入状态分配与SplitFuncs。将先小型验证strict/reset/数组语义，再以同一bound.compat IR做官方函数拆分，避免手动改数学或缩资源、避免继续原样llc。新编译若成功也仍须真实Host联合时序和数值资格。
起点main b7f05efe及同head CI43062307574成功，仅payload guard。工作树干净、约9.1GiB/56GiB可用，关键IR/native/参考逐hash复核。临时清单检查，既有数据清理0，无权重/输出/候选源码/rawlog上传，仅发布允许摘要与hash。

## 官方优化路径和明确终态
反证发现split阈值CLI在当前路径没有触发实际分割，先前小测试通过但helper数量未变，未用此冒切分资格或浪费全Host编译。改用官方--inline=false，最小函数数实际增加，7边沿/reset、4strict、8192数组对照再通过，保持原bound.compat MLIR。
新68893 noinline LLVM明确exit0/80.152s，3309函数，最大eval252408行，比418006减少39.6%；状态JSON与1633内容一致，20strict实际调用保留。新LLVM SHA edfd1d4947f9c043f284c0e5992e678addfa77dac54c12e5bc29e2d85470f2b3。基于真实成本下降再执行一次新机器码21635，exit0/42.434s，9809344B object SHAecc382dabe56fae335db054e420d5378e9ce4d7063a38589372177157deb8246；-zdefs链接exit0，libhost SHA6c7ec0a0437bfca256e8829d3a1c828b99beb55b41cc5f45cf7dbe1b74736e50。真正奏效的是Arc不内联，非单降llc优化。原失败不删除。

## 新联合有限运行
唯一1733_frozen_joint_reset_idle_v1真实Host+17native联调exit0/0.122秒，8周期（3reset、5idle）无launch。Host/native/layout hash与同singleton核实，每周期前后均2次low delta收敛；无AXI请求/result/completion/resetRequired，最终launch_ready=1，执行和内存计数0。
精确PASS_RESET_IDLE_ONLY：未运行旧profile/checkpoint，不是活跃负载、strict负例、完整prefill或利用率资格。strict回调存在但本次未故意触发fatal，不推定它已通过完整联合负例。下一步真实活跃刺激、AXI/命令闭包及严格异常验证仍需推进；五块完整模型仍0/5。
