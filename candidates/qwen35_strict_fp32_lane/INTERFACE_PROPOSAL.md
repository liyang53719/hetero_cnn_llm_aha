# 单 lane dual-mode FP32 原型提案

仅新隔离候选，不改原 BF16 文件、不接主阵列/Host，不扩 16 lane、UT 或公共入口。本批不授 JVM、RTL、数值硬件运行。最终资源意图是替换原 4096 中的 lane 配置而非旁增单元；本原型不证明物理面积/频率/netlist 不变。

## 唯一算术路径

新 HeteroFullFp32FmaPre：a/b/c 均 UInt32，recFNFromFN(8,24)，原 MulAddRecFNToRaw_preMul(8,24)，op=0。输出24/24/48位及54位 meta，与旧 BF16 Pre ABI 相同。

新 StrictFp32MatrixLane 使用此一个 Pre，加原 gemmini.HeteroBF16FmaMul、HeteroBF16FmaPost、HeteroBF16FmaRound 各一个，不实例化 MulAddRecFN 完整 FMA，也不实例化独立 MulRecFN/AddRecFN。原 Mul 的24×24+48→49整数路径、Post41bits+invalid、Round RNE/tininess-after-rounding 原封引用。四级寄存器顺序 Pre→Mul→Post→Round，一次只处理一个请求/一个 pass。第二 pass 回同一路径，不能算两个并行资源。

## 请求/返回 ABI

request: Decoupled，tag UInt32；mode UInt2；a/b/acc 各 UInt32。只有 idle 时 ready；result held 时不接下一请求，不同周期流水并发暂不做。invalid请求也必须先被接纳，随后仅一个 held terminal。

mode0 = LegacyBf16Fma：a[15:0]/b[15:0] 为 BF16 raw bits，a/b 高16位必须0；acc完整FP32。输入 mux 将 BF16 拼16个0给新Pre，只做原单FMA。此模式返回原 IEEE raw result/flags，不套 GDN finite/fatal30策略；NaN/Inf/OF可作为原算术结果返回，不把 status=OK 理解为有限数值。错误高16位是编码拒绝，零pass。原生产BF16配置与其所有处理原样不动。

mode1 = StrictFp32MulAdd：a/b/acc是完整binary32 bit-pattern；三者任一 NaN/Inf 在 admission 拒绝，零pass且所有算术flagsValid=false，不能伪造“硬件运算产生NV”。其他mode拒绝，零pass。

response: Decoupled，所有字段在 valid&&!ready 时冻结。
- tag32、mode2、status3。status0=OK，1=BadMode，2=BadEncoding，3=NonFiniteInput，4=MulFatal，5=AddFatal。
- product32、productValid；value32、valueValid；accCommit。
- mulFlags5/mulFlagsValid、addFlags5/addFlagsValid、fmaFlags5/fmaFlagsValid。
- passesCompleted UInt2，0/1/2，只在真正完成 Round 后递增。
输入拒绝所有数据/flags为0且对应Valid=false。BF16完成 valueValid/fmaFlagsValid=true、passes1、accCommit=true，product/add/mul字段无效。Strict Mul完成始终保存原product/flags（即使fatal），Add尚未运行时valueValid=false。Strict Add完成保存原value/flags（即使fatal），仅成功accCommit=true。没有全局state/root、generation发布或DDR事务。

## 严格两 pass

M：a=request.a，b=request.b，c=符号为a.sign xor b.sign的FP32零。Round结果就是候选MulRNE；flags按NV16/DZ8/OF4/UF2/NX1解读。fatal=(flags & 30)!=0或结果exponent全1。exact subnormal与±0必须接受；NX单独允许。MulFatal保product诊断与flags，直接held terminal，不得执行Add。

A：a=已舍入product，b=FP32 +1(0x3f800000)，c=原acc，经过完整Pre/Mul/Post/Round再次RNE。p×1精确，但仍必须实际使用共享算术链。AddFatal保诊断，不提交。成功仅在第二Round后accCommit。不得折叠成a*b+acc的一次FMA，不得first pass更新acc，不得让Mul overflow经acc抵消后变成功。

本lane没有内部持久accumulator bank：acc是显式请求输入，成功value是提交建议；上层未来负责按K升序接力。本批无16词全组故障屏障，不能冒称已完整替换原vector16组语义。

## 状态与边沿

idle→pre→mul→post→round。BF16 Round或任一fatal到reply；strict Mul成功从round回pre，pass切为Add且使用已注册product。Add Round到reply。reply仅在result.fire回idle；不做同边沿refill。

从request.fire边沿0起，Pre/Mul/Post/Round在边沿1/2/3/4。无回压BF16最早result.fire边沿5；strict Add的四步在5/6/7/8，最早result.fire边沿9。此为该单请求源级状态推导，不是4096吞吐或时序资格。等待result.ready不会继续算术或改字段。

内部reset丢弃未退休请求并清所有valid，不产生假成功；它不涉及外部共享服务，故不需要捏造DDR drain。没有abort端口或全局恢复承诺。错误可以在terminal退休后接受新请求，所有工作都在内部固定寄存器，不能将此规则迁移给有外部响应的owner。

## 独立小参考测试计划（root另准执行）

纯stdlib软件路径分开：一个整数binary32算术模型（exact integer significand/exponent + RNE）用于候选两pass语义；另一个Fraction有理数参考，通过独立的相邻binary32候选距离/偶数选择实现RNE，先独立Mul，再独立Add。两个路径不得共享舍入函数，不使用Python float作oracle、不导入DUT/Scala/现模型代码，不编译native。参考只覆盖有限输入与显式非有限拒绝；BF16 raw IEEE NaN payload/HardFloat特定传播须以后真实硬件测试，不由软件canonNaN冒称证明。

小集合包括低16fraction bits、RNE ties、±0、精确subnormal、tiny inexact/underflow、Mul overflow后 fused cancellation反例、Add overflow、每passflags、MulFatal无Add、编码与NaN/Inf拒绝、held reply/第二offer/复位、两pass独立寄存、请求tag身份。可加有限固定种子的bit-pattern对照；不以随机替代定向例。

测试结论仅 SOFTWARE_REFERENCE_AND_PROTOCOL_MODEL；Scala源码/编译/CHIRRTL/真实数值/握手各层单独。当前无Treadle依赖，不发起下载、不伪称硬件已执行。
