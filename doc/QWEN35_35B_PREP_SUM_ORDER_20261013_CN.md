# 35B Prep 固定FP32归约次序接线（2026-10-13）

## 范围

显式 torch_2_10_cpu_default_f32_8lane_4ilp_128 policy，仅用于35B GROUPED布局。
旧默认 legacy_ascending128不变，job/owner/CLI/source identity必须一致。
实际重跑完整已实现前缀：同memory/Scalar的RMS→QKV→Conv、RMS→A/B→ACK重排→Prep。
不将旧中间raw当新producer，也没有改变exp、Softplus、g精度或其原始诊断口径。
本批没有生产Chisel归约绑定、32头chunk执行或完整block/RTL验收。

## 官方固定后端证据

Torch 2.10.0+cpu，commit449b1768410104d3ed79d3bcfe4ba1d65c7f22c0，
x86_64、ATEN_CPU_CAPABILITY=default、线程1/1、RNE/渐进下溢。
[官方SumKernel.cpp](https://github.com/pytorch/pytorch/blob/449b1768410104d3ed79d3bcfe4ba1d65c7f22c0/aten/src/ATen/native/cpu/SumKernel.cpp)
SHA256 9b88aa14e626dd708e50816a5ca89acfc66798226dc82501cf1857caebe96f95。
显式acc_type<float,true>仍为FP32；DEFAULT Vectorized<float>为8 lanes。
实际sum入参连续FP32 M16=[1,32,16,128]/stride[65536,2048,128,1]，
M128=[1,32,128,128]/stride[524288,16384,128,1]。
安装headers与固定libtorch_cpu链接的独立iterator探针，两形状都给size0=128、
size1=512/4096、byte strides[0,4,4,512]，命中inner vectorized分支。
4路ILP每路4次累加，随后按group左折叠，再8lane升序左折叠。
这不泛化成其它设备、后端、shape或stride的统一规则。

独立候选自行读取真实BF16输入计算，未读取官方sum作为输入：
M16/M128全部9216个sum、1179648个Q/K输出逐位一致；width4/16、ascending、
平衡树、连续16分块等对照不吻合。12个真实head另经既有PrepScalar接口也精确。
这些host探针只是先验证次序，实际生产者运行另计证据。

## 真实资源与寄存器生命周期

按lane=0..7、group=0..3、t=0..3，地址lane+8*group+32*t；每组与每lane
立即左折叠，只保留total/lane_sum/group_sum/temporary四个FP32值。
128word head cache在归约阶段只读，归一化阶段才写回，不需要额外DDR读取。
每head执行128 MulIeeeRne+127 Add；仅省略非负有限square域严格等价的+0。

生产GdnInputPrepOwner现有相位寄存器可作以下映射（尚未绑定生产Chisel）：
- accumulator：total，整个head归约存活，归约后保留给epsilon。
- inverseNorm：lane_sum，每lane首组覆盖；归约结束失活，inverse响应重新写入后normalize才读取。
- positive：group_sum，每组首square覆盖；归约结束失活，V写ACK后softplus响应重新写入后logDecay才读取。
- temporary：当前square/add结果；最终sum须回写给原epsilon输入，再沿root/inverse路径运行。
旧7bit lane计数器c可用Cat(c[1:0],c[3:2],c[6:4])重排地址；normalize前归零。
无需新增32accum阵列、FP64、新Vector或新SFU。软件局部变量按上述相位重用，
不能把可行寄存器映射当已通过综合或RTL时序证据。

## 门与运行边界

同owner abort/readfault终态后reset再执行、policy错配、数值溢出/非有限不publish、
原cache不变、真实DDR读写计数不增均有小测。现有传输drain/ACK控制未改。
首轮测试错误地在admission后修改policy，被source identity拒绝；修正为显式构造新owner后重跑，
失败结果没有继承为PASS。旧0.8B默认和g原诊断需在全冷门继续回归。

新M16/M128的完整原始摘要、逐角色误差、源码与native SHA、读写/Scalar/Matrix计数
见配套机器摘要；Q/K逐位吻合也不等于Prep整体或完整block通过。
g仍有原误差，history仍未发布staging，完整周期/占空比/有效MAC利用率未知。

## 本次实际结果

M16/M128各72执行源、10native前后不变，原冻结输入与上游全部输出SHA不变。
各七真实终态；M16 Q/K各65536、M128各524288个元素逐位一致；V/beta继续逐位一致。
g仍原M16 33ULP、M128 35ULP，误差逐字段与旧结果相同，不授予Prep整体新PASS。

Prep实际DDR M16读401408B/写819200B，M128读3211264B/写6553600B，均与旧一致。
Scalar Add分别减少1024/8192，其余op不变；transport ticks亦不变，不能据此声称硬件周期不变。
Matrix每档执行2164260864 FMA；M16有效270532608，M128有效2164260864。
固定资源Matrix4096/Vector16/Scalar1不变，M16物理padding不能计入有效MAC。

当前局部归约调度是数值对齐候选，不是最终流水优化；四寄存器串行依赖深度需要生产绑定后测量。
既有软件tick仅表示事务握手，不含Scalar实际流水延迟，不能推导80%/90%利用率或占空比。

全冷门526项/47套/147源零skip、前后源码不变；指定计划清单pytest91项通过。
