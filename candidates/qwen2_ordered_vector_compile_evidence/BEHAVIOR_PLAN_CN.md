# 下一片：真实 core/client 最小行为验证计划（未执行）

当前class compile只证明固定源码可编译。源码AST门控、Python reference、compiler成功都不能证明Chisel构造正确、score SRAM写使能、真实同拍优先级或flags连线在电路中工作。

## 最小目标与真实阻塞

1. 先对候选开关false/true分别进行有界elaboration检查，验证端口/宽度/require/组合连接、额外fault寄存器计账；这是新阶段，不继承class PASS。公开profile仍禁止official packed + Elementwise loan / H2048 RMS borrower。
2. 建立实际Qwen2ContinuousBlock与未改PackedAttentionStreamClient的小型Chisel测试harness。不能另写一套fold控制来代替DUT，也不能把独立Elementwise ALU当成core原16ALU。
3. 原仓库没有专属PackedAttentionStreamClient Scala Spec。可复用 BlockScalarFloatSpec 的严格flags边界向量、ElementwiseRegisterLoanSpec / ReplaySpec 的握手/取消观察方式，以及 production_qkv_reduction/compiled_control/source/ProductionQkvProtocolSpec.scala 的Decoupled事件计数方法；不能直接把这些旧Spec的通过记到本片。
4. 真实执行还需明确测试backend闭包、现有 SRAM/HardFloat/blackbox实现和工具版本。不能默认ChiselTest不生成RTL；许多backend会emit FIRRTL/SystemVerilog或调用Verilator。因此本轮没有运行任何该阶段测试，下一片先列出实际命令和资源并批准其边界。

## Harness边界

- 使用真实ownerJob、memory request/response及packed Matrix group/step/result/done端口把core推进到QK，不poke内部FSM/acc来跳过合法初始化。
- Matrix endpoint可使用测试输入脚本按8个已接受step提供完整固定结果tile；这只隔离consumer控制，不声称验证Matrix FMA或完整Attention数值。
- 用测试专用、只读观察端口/注解记录state、lane、selected、fault bits、score-write(index/data/enable)、maxScore、packedCommitted、result-ready、completion和三类feed debt。插桩另存patch/hash，不改变生产算术或反馈控制；不能用probe结果驱动DUT状态。
- 首批只M1/M2/M3小owner任务（三key故障顺序反转需合法M3）、少量固定BF16/FP32字，不加载权重、不跑完整block或M128。tail16需从合法任务推进，先独立预算再加入，不能通过强制FSM伪造可达性。
- 每个case设固定最大接受事件数、最大时钟步和wall时间；M1、M2、M3分别设case预算；初次每case预定不超过1个CPU、2GiB运行内存、60秒和100k步硬截止，实际backend若无法在此范围准备就停止报告，不启动无限编译/仿真。

## 必做场景与可观察验收

A. 提前done同拍竞争
- 在scan、fold、scale、retire各阶段，驱动合法held result同时出现matching提前done，以及foreign-tag done。
- 特别在首key退休与最后key退休同拍注入，要求该拍score-write为0、packedCommitted不置位、result不被成功消费。
- 后续Protocol错误/poison进入原client draining；foreign tag不能清除当前group债务。这里必须实际执行电路，不能再次用提取orderedSafe布尔表达式代替。

B. 异常发现顺序与退休顺序
- key1在末stripe发生Add overflow、key2在首stripe为NaN：key2先发现不应抢先失败或消除key0已提交前缀。
- key1在scale发生inexact UF、key2较早fold overflow；只提交key0，再按key1失败。
- 覆盖BF16 dot溢出、NX-only、exact subnormal、±0与舍入临界。按已有严格参考逐字比较，不用松容差。
- 查看真实ALU flags(4,1)归约，明确UF fatal、NX-only允许；finite Add/Mul没有可达DZ，不能虚报DZ硬件激励覆盖。

C. Tail与结果保持
- 首批tail1/2，随后在有界预算内tail16。inactive cells填NaN/Inf及可能导致flags异常的值，active结果必须不受污染。
- 核查result头从scan起到最后score写入后才ready；正常最后key保持count−1，不回绕；done/completion回压期间不释放ownership、不开始下一组。

D. Abort与已接受债务
- 在scan/fold/scale/retire、最后提交前一拍及提交后ACK前注入abort/resetRequired路径；abort后不新增score写入。
- 对已接受memory/local/scalar事务分别延迟响应，核实原tag匹配清债和finish等待。新fold路径不新发这些事务，不能为测试凭空制造不存在的债务。
- result、done、completion必须按原client协议排空；禁止用测试端直接清busy或直接调用抽象drain集合。

E. 共享资源/borrower互斥
- packed profile + Elementwise loan/H2048 borrower应在构造期按既有require拒绝，class编译并未执行该require。
- direct core允许externalScalar=true时，测试外部request.valid=1且ready=0合法等待，不应误触“已占用”断言；检查只有core idle时接受，owner launch与真正已接受Scalar请求互斥，结果回压期间不得被新QK覆盖。
- 对允许的原norm/rope/bias与新QK状态切换，监测vector输入选择，不同state不会同时驱动有用运算。不要为通过测试扩大新profile允许配置。

## 明确停止条件

必须取得DUT实际波形/事件计数、原始失败记录和与所测source postimage绑定的结果。仅elaboration成功不足以关闭A–E；少量DUT场景成功也不等于完整Attention/Matrix数值、M128、面积/时序或80%/90%达标。任何失败保留、先定位，再以新的小补丁和新receipt验证，不改历史记录。
