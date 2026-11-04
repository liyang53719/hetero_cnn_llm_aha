# GDN32与受控abort统一源候选V2

状态：源码集成与有界纯测试；未编译、展开、RTL仿真、EDA、DUT、发布或激活。基线兼容源8eb141f0cb3d9fab16f74c2b1e2704e3b2f966ab保持不变，original97358仍UNKNOWN/reserved，不能继承旧artifact PASS。

## 实际统一选源

原legacy159源，新增ExecuteOwner32、SelectedExecute wrapper及CancellableHeldDecoupledOffer，共**162唯一源**。新source selector仅显式`gdn-chunk32-abort-v2`启用，默认legacy159不变。新helper在162列表中唯一替换原helper，固定同一Top构造器enableChunk32=true供五profile共用。实际改动贯通Collection、p0_resident_observation的Kernel、protocol、wiring、moe_router_score_observation的Top、adapter及共享hub/coordinator；不是未选中的同名副本。

共享Vector32仍只有一个BankV4；Chunk32独立slot12/kind11/stage79，Derived16保留slot10，RMS保留slot11。真实Guard/RawPrep事件mint三个lease，Scalar计数不变，Derived为H*C*4704，Execute32为H*C*329472+4*M*H，总vector=H*C*334176+4*M*H；成功退休仍核对真实fire/issued/returned。policy0/3与规范format4、逐lane升序K、Mul后Add、BF16取位不变；五内存client/17-client hub与64B ACK保留。

## 独审后的abort范围

受控abort覆盖Execute32未接受offer显式cancel/ack与匹配的已接受债务排空；ACK与request.fire互斥，取消不增加accepted/issued/returned。已接受memory/vector工作不能取消。leaf只有债务清零、无quarantine后才产生唯一held故障receipt；coordinator在opt-in模式记实际部分ACK并发故障terminal，禁止staged success。默认构造器保持legacy行为。

终态是**有条件的**：外部服务必须返回匹配响应、terminal接受、Guard身份稳定且其他client可排空。missing/wrong/unmatched响应保留债务并安全隔离，不伪造退款、ACK或全局reset豁免。RawPrep/state/load/derived/transpose、Guard身份损坏等并未获得全面abort闭包；不能声称全局bounded terminal/drain。详情见ABORT_REPORT.md。

## 验证与发布边界

源选路/计数/身份/结构纯测试及abort参考协议模型均以普通和-O模式运行；这些不执行Scala FSM、不证明真实电路数值或周期。唯一Vector32、4096MAC及122外端口仍须新Top elaboration/resource inspection确认；本阶段CI只编译，不调用Top或ChiselStage。

发布布局为candidates/gdn_chunk32_actual_v2_20261104。selector默认仓库root或显式--base，测试可用GDN32_BASE；PUBLICATION_MANIFEST只有相对路径与hash。原生产generation/admission白名单不扩大，新增generation identity单独绑定source-only compile，不授权数值执行。唯一新nonce CI需父级独审后第二提交激活；首source提交休眠。不上传binary/cache/artifact，stdout仅有限安全摘要。
