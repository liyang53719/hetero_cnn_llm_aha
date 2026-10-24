# QK16 ordered vector fold/scale：独立 Chisel 控制补丁

资格：SOURCE_COMPOSE_PASS / BOUNDED_REFERENCE_TEST_PASS；COMPILE、ELABORATION、RTL、频率/面积、完整 M128 均 TEMP / INCOMPLETE。不是80%/90%利用率证明，model step和主机耗时都不是硬件周期。

本包不直接修改生产 Scala，不替换旧 pins。ordered_fold.patch 必须应用在指定 selected production postimage，不能用于 bare-main 原源码。新增开关 enableOrderedVectorQkFold 默认 false，经 HostBlockCollection→HostBlockTop→QwenOwnerKernel→现有 Qwen2ContinuousBlock 透传；所有旧 emitter 和调用点默认关闭。开启要求已选择 production packed QK16、official BF16 owner，且 headDim=128。

## 已实际实现的源码改动

- 保留现有 core 内16个 HeteroFP32Alu 的实例引用，显式接出16组原有 exceptionFlags；不是新增通用 SFU、Elementwise engine 或第二组ALU。
- 追加 attVectorScan、attVectorFold、attVectorScale、attVectorRetire，旧103个state编码不变，107个仍在原7-bit范围。
- 最后 Matrix result 可见时清零既有 acc[16]，先16 stripe finite scan，再按 r=0..15 执行 acc[j]=Add(acc[j], live.value(r)(16*j+r))。不复制完整16KiB tile。
- 复用同一批ALU做 BF16(dot)→FP32 strict Mul(original scale)→BF16(score)。检查 NV/DZ/OF/UF 和全部可达输入/结果有限性；NX单独允许。不使用 GDN MulIeeeRne 的 UF 豁免。
- 16个 sticky fault bits 记录各key是否失败；后key提前算出异常不会提前发布。按原key顺序提交score/max，遇到该key的sticky才走原 packedSelectedFault→fail。
- 所有新增状态的推进和写入均由 packedBusy、!poisoned、!resetRequired、!port.done.valid、result.valid、!matrixFault、!address_error 门控。特别阻止提前done与result同拍出现时写score，不能等待下一拍resetRequired才停。
- tail lane及fault lane不更新acc/fault；所有新增状态先把16路ALU输入置零，仅active且无sticky的fold/scale lane覆盖。尾部结果/flags不得影响其他key。

## 真实 client 生命周期与资源审计

PackedAttentionStreamClient.scala 完全未改，SHA256在 PROFILE_PINS.json。并没有用微模型的抽象drain集合替换该client。

1. live result要保持到最后score写入；最后key不自增，防止4-bit packedSelected回绕。只在最后成功写入时置 packedCommitted=true，并转原 attNextKey。
2. 原 c.io.result.ready := packedCommitted && !poisoned 未改，故最后写入之后才允许消费结果；原completion.ready、packedOwned清除及下一组条件未改。
3. 出错退休仅置原 packedSelectedFault；原末尾fail置poisoned，驱动原 c.abort。原 packedMemDebt/packedLocalDebt/packedScalarDebt、tag匹配、已接受事务排空和finish条件整段逐字保留。
4. 新状态不发 read/localRead/calc，也不直接改 client ready/completion，因此没有新建memory/local/scalar debt。不接受新的job仍由原owner和client忙条件保证。
5. badResult可让client当拍撤销result.valid，而poison下一拍才可见；新增状态必须同时检查result.valid。提前/foreign done亦必须当拍门控。
6. core vector的原有norm、dense bias、rope、biasSum赋值均由互斥state选择。external Elementwise loan是另一个engine，并且official模式已有require禁止loan；不能把它当本次复用的ALU。
7. 外部 Scalar 的未接受 request.valid 可以在ready=0时等待，不等于资源已被占用。独审发现并移除了这类误触发断言。只保留“新状态不向真实scalar发request”的断言；既有externalScalar只在core idle接受请求，ownerJob.ready排斥其busy。

## 资源与时序边界

新增数据寄存器只有16个sticky bool。复用acc 512位、lane 4位、packedSelected 4位、原maxScore、packedCommitted、score SRAM；未新增tile/score寄存器bank或全局cache。16组5-bit flags是组合连线，不是80位寄存器。新增state未扩大7-bit编码。

这只是源码级资源审计，不是综合面积证明。组合stripe mux、BF16物化→Mul→物化路径及fanout尚未做时序验证，不能宣称1GHz、II或频率通过。虽移除了该profile中串行QK Scalar调用，仍未建立同源完整block周期分母；PV6另需独立接入，FFN协议不在本片范围。

## 可复现组合与小测试

原 selected tree需要包含 PROFILE_PINS.json 指定的三份Scala及未变client。main checkout包含原有Python reference/client与已发布微模型。

    python -I -B candidates/qwen2_ordered_vector_chisel/prepare.py --selected-root SELECTED_TREE --out NEW_OVERLAY
    python -I -B candidates/qwen2_ordered_vector_chisel/test_contract.py --selected-root SELECTED_TREE --source-root MAIN_CHECKOUT --micro-root MAIN_CHECKOUT/candidates/qwen2_ordered_vector_fold -v
    python -I -B -O candidates/qwen2_ordered_vector_chisel/test_contract.py --selected-root SELECTED_TREE --source-root MAIN_CHECKOUT --micro-root MAIN_CHECKOUT/candidates/qwen2_ordered_vector_fold -v

prepare是严格上下文纯Python patch应用器，核验输入、补丁及输出SHA，不使用Git或外部patch进程，不创建完整编译闭包。输出是三文件overlay。

测试范围：9项实际源码契约检查（含orderedSafe全部128种布尔组合）、16项原样现有PackedClient单测、3项新微模型与现有PackedClient集成测试（tail 1..16、live tile持有、结果/完成回压、顺序fault/abort、提前done门控）。另运行已发布微模型的12项精确算术回归。normal、-O、-I、-I -O 四模式各28项contract/client测试和12项微模型算术测试通过。所有加载的原样AST及micro model均pin到main 529da68（与3c2283a相同字节），未import生产module prelude。

重要区别：这里的PackedClient是仓库现有Python协议reference，ScriptedService不执行Matrix算术；Scala client路径是逐字保护和独立源码审查，不是RTL等价测试。提前done用例只验证提取的门控及微模型停步，未向Python client注入提前done，亦未执行Scala同拍竞争。source contract和Python算术通过不等于执行过新增Chisel。尚无经过验证且可直接运行的Scala compile-only工具闭包，本批没有下载或重建工具链，也没有调用任何emitter/test生成RTL。compile保持TEMP。

## 下一步

先补齐可复现有界compile-only闭包，显式报告命令/资源后再编译；之后独立验证elaboration/真实client故障竞争与RTL数值。仅在用户批准的下一批范围内推进，不能继承旧M128或旧利用率PASS。
