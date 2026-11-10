# hetero 21:33：编译式真实传输适配器与完整M128推进（INCOMPLETE）

## 实质编码与验证
先核 main 282b44c 与 CI 42897116687 success（仅 payload guard）、旧作业终态及临时资源，无重复启动。实际profiling定位Python逐帧snapshot/slot解析与FFI开销：500次settle基线1.106秒，snapshot缓存0.491秒。snapshot独立24随机完整state、435有效bit、200padding、5边界负测通过，304观察槽无删减。
随后实现C++传输settle+step，只搬原slot并调用同一compiled Host及17真实native，不计算DUT算术或替换4096资源。独立审查发现初版高位静默mask、partial-create清理、固定长度及异常后重入问题，修复并保留初版。修后真实1000 driver帧逐一比较368B输出、全部345命名slot有效位及完整1624112B原始state，全部一致，无padding/bookkeeping豁免。API负测保持first-low/high相输入稳定、错误poison、尺寸/高位拒绝，重复high无重复推进；故意采post-edge负版本在第28帧被差分拒绝，未用于实际运行。原fatal与preedge时序不改。
1000帧回放最好1576frames/s、约525cycles/s，包含原core/native但不含driver IPC，仅软件回放速度，不是硬件利用率或完整数值PASS。

## 预算与完整链
源码审计：Qwen2 M128首Norm仅1536逐行串行Add的周期下界786432；L3事务下界86528，均非RTL实测或完成保证。没有再次重复Qwen2首行120秒短跑。经资格后唯一L3完整M128原真实输入采用600秒/1000000 active-cycle预算，固定同Hostlib/state/schema/17native，只改运行输入与测试预算，不改硬件。终态见后续记录。

## L0并行实质准备
原冻结0.8B L0 M128完整17命令/219描述符输入（真实权重、原caller synthetic dyadic hidden及既定cold history/state）接同Host入口，原Config+mmap SHA重验及dt_bias损坏hash负测通过。只在原预留空间补32B dt_bias总线尾padding和命令/描述符metadata尾padding，原参数不变，未预装中间值。入口编译检查通过，尚未运行；原head4 underflow FAIL/fatal保留，不能迁移候选数值通过。

## 范围、阻塞、后续
五块完整数值仍0/5；35B L0/L3完整真实冻结输入缺口未绕过，MoE同分契约未改。尚未最终RTL回放，80%/90%完整周期利用率无实测。下一步沿同编译硬件实际完成原完整模型数值链，不制造receipt、缩MAC或用M1循环冒chunk。
仅发布允许摘要/hash，候选源码、原始日志、IR/native工具与真实权重均本地保留，不绕之前审查拒绝；临时清单保留、无清理。

## 唯一L3实际600秒终态与精确首Norm数值
原身份PID8/start7399594的600秒任务终态INCOMPLETE：794634帧、pc1、issuedJobs2/completed1、DMA17050、pipelineIssues1921、resetRequired0、无FINAL。已从首Norm推进到Dense，未完成22命令整块。pipelineIssues是issue计数，不是错误数，也不能换算为完整block MAC利用率。
真实clean ordered completion与AXI drain后导出的input_norm.actual.bin，128×1024 BF16、131072元素/262144字节，与已pin独立参考逐字节及逐元素完全一致，差异均0，SHA256同为ab1f29183a7fe678d9dcbd87cc7bc680db323bd75ec7a839ab154a2e41e7fab9。输入/gamma绑定hash重验，独立RMS重算亦与既存参考一致，未向DUT注入参考。**PASS精确范围仅该0.8B L3首Norm全128token数值**，不是完整block、五块、最终RTL或新32lane硬件PASS；五块完整数值仍0/5。所有原任务已终态，不重复跑。
