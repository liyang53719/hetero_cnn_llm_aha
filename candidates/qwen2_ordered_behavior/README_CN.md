# Ordered QK：软件 edge 行为资格化增量

状态：软件模型有界测试；硬件仍 TEMP / INCOMPLETE。本包不执行 Scala/Chisel、elaboration、RTL、native Matrix、完整 prefill 或 M128，不修改原路径或冻结证据。模型 tick 是同步离散事件，不是已测硬件周期。

## 本片计划与复用边界

1. 先核对已有微模型、28项源码/旧client测试和 compile-only 行为计划。原 Python PackedClient 是 service/request/reply 协议，含显式 PackedConsumerAck、ticket/epoch、bank-write 债务；selected Scala client 的 ACK 是 result.ready，只有8个状态，不能拿旧 Python client 当成它的同拍实现。
2. 新增 stream_client.py：显式实现 pinned Scala 的完整8状态控制，先计算前态 ready/valid/fire，再按源码 when 顺序更新寄存器，包括末尾 unexpected terminal 和 abort 的覆盖优先级。没有从 AST 抽取一个布尔门就声称模拟 client。它仍是人工翻译的可执行软件模型，不是 DUT，也不是等价性证明。
3. control.py 将该 client 与既有 pinned OrderedVectorFold 的 scan/fold/scale 算术组合；退休自己执行，保留最后 selected=count−1、score/max 顺序写、packedCommitted 后一edge才允许 result ACK。实际消费/完成/tag/abort 用8状态模型，不调用原微模型的抽象 drain 集合。
4. 复用原样 ExactScalar/Fraction RNE helper 和原 service-client 的16个测试，加载已pin定义 AST、跳过 native/NumPy 模块前言。旧client回归仍单列为旧service协议通过，不记为新StreamClient覆盖。
5. 每个case固定步数上限，单CPU、CPU20秒、地址空间256MiB；normal/-O/-I/-I-O 小回归。不是已有完整prefill加速验证，不申请昂贵工具或新CI dispatch。

## 源码对应及不能证明的部分

输入身份：main 172d67e569e0cee72d92cb72c2c94545b36919f4；候选控制于5a8e99c发布。SOURCE_PINS.json 标注 selected core/client SHA256。core是recipe组合后再应用 ordered_fold.patch 的postimage，不是bare-main Qwen2Block。源pins稳定绑定阅读对象，不是执行Chisel的证据。

- stream_client.py 的 peek 对应 PackedAttentionStreamClient.scala 中 default wires 和 enabled 内组合逻辑；tick 依源码顺序执行 start/group/operands/result/done/completion、reply abort、unexpected terminal、最后 operational abort。disabled不握手。descriptor 未初始化用None表示，不伪造reset值。
- control.py 的 feed→scan 是最后 result 可见后开启候选控制的切片边界。没有重建 owner start、Q/K缓存装载、DDR gather地址、Matrix8步FMA；测试通过真实模型start和8次operands握手到awaitResult，不直接poke client FSM。
- arithmetic.state scan/fold/scale 对应 attVectorScan/Fold/Scale，输入从 live tile.value[r][16*j+r] 读取，active tail以外访问直接失败。旧微模型内部额外 observation/debts 字段未用于任何清债，不能据Python对象内存声称硬件资源。
- 算术调用原严格参考，NV/nonfinite 在scan或finite检查拒绝；有限Add/Mul OF及inexact UF fatal、NX单独允许、BF(dot)→Mul原scale→BF(score)。模型没有模拟 HardFloat flags 导线，不能声称实测NV/DZ pin；DZ在该有限Add/Mul域不可达。不可达NaN payload不做宽松替换。
- retirement 对应 attVectorRetire：后key错误只保存sticky直到按key退休。score观察列表对应已有SRAM写事件，maximum对应maxScore。最终selected不回绕，committed为寄存器值。
- FeedDebts 对应core末尾三个accepted bits，memory只匹配request.tag，local/scalar不杜撰tag。接受事件来自显式feeder边界；本模型不生成memory/local/scalar请求。故障同edge的已接受工作保留；finish+poison才给逐类清债ready；错误memory tag不清债。fold阶段不允许凭空制造新feed接受。不是模拟整个memory fabric/writeback fence。
- ScalarBorrower 对应idle&&!poison&&!busy、request.valid阻止owner launch、accepted request持有busy直到result.fire。请求valid=1/ready=0不是已借用。profile validator复述现有official packed禁止Elementwise loan；它不执行Scala require。norm/rope/bias内部vector mux、H2048 borrower、所有owner状态互斥没有硬件行为覆盖。

## 必须保留的真实细节

提前done与首/末score退休同edge：core抑制该edge算术/score写，client下一态变draining+poison；foreign tag不done.fire。

但当最后score已在前一edge提交、packedCommitted已为1，result ACK与提前done同时到来时，原client允许result.fire，同时因提前done将状态置draining且poison。不得错误宣称这种场景“结果永不消费”：正确的软件验收是没有成功completion，必须继续等待匹配done并返回error。这是原组合控制语义，不是新增硬件修复。

已发生故障后的client.abort来自registered core.poison；测试分开观察fault edge、下一edge abort、draining消费。取消不制造未接受事务，早done/abort不撤销已提交score前缀。matrix_fault/address_fault是已有核心故障输入，不添加虚构的core external abort端口。

## 干净 checkout 复现

    python -B candidates/qwen2_ordered_behavior/test_behavior.py --source-root . -v
    python -B candidates/qwen2_ordered_behavior/test_stream_edges.py -v

两命令可分别加 -O、-I 或 -I -O。test_behavior 默认使用同checkout的 candidates/qwen2_ordered_vector_fold/model.py；审查环境可用 --micro-root 指定只读原包。脚本明确插入自己已解析目录并验证本地模块来源，不添加生产源目录到sys.path。开始运行前核对全部原始source和micro hash，任何漂移失败。仅标准库，无工具下载、自动编译或RTL生成。

## 余下资格

新软件翻译可能与Chisel存在未发现偏差；不能证明组合连线、位宽、Chisel last-connect/elaboration、SRAM写使能、真实ALU flags、矩阵数值、所有accepted feed可达性、完整owner borrower状态空间。后续在用户允许的阶段才考虑实际DUT验证；本批不改原compile-only证据，也不升级为完整prefill、M128、1GHz、80%/90%或完整block周期PASS。

## 本批实际结果

normal、-O、-I、-I -O 各33+15=48项通过：32项新增软件行为和16项原service-client回归，四模式共192项执行。独立复核 -I/-I -O 各48项通过。validation/RESULTS.json记录逐命令退出值、资源和日志hash。PV count=128仅是128次无算术控制握手测试，不是M128 prefill作业。

独立审查发现两个新增Python模型缺陷（先更新state导致漏掉error completion；地址/协议优先级颠倒），先以两条新增回归真实复现失败，再修正为所有条件使用前态并按源码覆盖顺序赋值。失败摘要及原始日志hash在validation/DEVELOPMENT_FAILURES.json；它们不是被实测的Chisel缺陷，旧失败未追认为PASS。
