# Qwen3.5-0.8B chunk64 DerivedAndPair：独立源码批

本批只提供完整 phase2 控制器源码与对应纯 Python 小模型/模拟服务测试源。没有执行 Scala、Chisel、RTL、真实 Memory/Loan/Scalar 握手或独立 FP32 DUT。本目录的测试结果应另封，不因 manifest 或源码存在就取得执行权限。

## 唯一生产增量

`source/GdnChunkDerivedAndPairOwner.scala` 新增独立 owner 及私有 job/result/decay 类型，不改任何基底源、顶层、Host fence、public/recurrent M1 门或已有服务。owner 不实例化算术模块，只借原 MemoryRequest/Response、GdnScalarClient ExpNegative4 和 ElementwiseLoanPort Add1/Mul2。

完整合同在 INTERFACE_CONTRACT.md。24 项固定依赖位于 INPUT_PINS.json，原 21 源与远端固定 commit `adefaa78c2d313d9927b4e87550dddc926b3c605` 一致；另 3 项是此前独立候选的 ChunkProtocol、AddressPlan、LoadPrep owner，不冒充远端实现。

- 每个 head/chunk 完整64行，包括 M16 的已准备 padding scratch。
- 相较原软件先补读 gates[63] 一次，不改 phase1 结果 ABI；共3681读、2816成功写ACK，scratch180224 B、external output/state0。
- Exp2209、逻辑单lane Add2144、Mul16 2560；Add另外15 lane为+0填充，不计 useful。
- 四个512-bit payload寄存器合256 B。另8个FP32 scalar words和context/控制/计数寄存器单列，不声称256 B是owner总资源。
- 原tuple四结果全部成功才开始KB/KBG/QG/KE写；不提前spill，不批量重排exp/pair。
- 新私有decay结果仅最终pair ACK及全部计数成功后有效，绑定完整accepted context/head/chunk；可信scheduler保存至同身份phase15，不发布root或generation。
- Loan abort/resetLoan恒低以允许held错误结果退休。失败后owner锁定，恢复须协调共享fabric；没有局部clear、无tag Scalar隔离或跨命令防重放的虚假承诺。

## 小控范围与执行门

TEST_COMMAND.json 给出提案：冻结 `/opt/.../python` 3.12，`-I -S -B`，一次10秒外墙钟、单CPU、256 MiB AS，三个精确只读源根。只能在独审与root单次准入后执行，作者不自行跑。

测试应先核本包与外部pins，再从已核raw bytes装入纯Python模型，执行显式pre-edge请求/响应握手、完整stage顺序/ACK/身份/held结果及失败控制，最后复核pins。服务由纯整数binary32 RNE和legacy P7 Exp模型提供；literal向量、模拟模型与参考循环一致仅证明这些软件合同，不是独立HardFloat数值验证，更不是Scala或真实ACK。模拟错误应明确标注，exact subnormal Add不应伪称自然underflow。

不得把理论服务槽、局部操作数或本小模型当硬件周期/完整block利用率；没有完整chunk、M128 fullblock、RTL或80/90%指标资格。Treadle依赖获取阻塞与Qwen2 UNKNOWN作业保持原状。本批不下载、不编译、不生成新RTL，也不读取旧未封值流。
