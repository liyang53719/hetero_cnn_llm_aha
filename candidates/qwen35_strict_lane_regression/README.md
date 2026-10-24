# Strict FP32 lane 定向回归源码

TEMP / 临时待验证：仅源代码与 fixture 检查通过，Scala 编译及硬件仿真尚未运行。

新增真实 ChiselTest / ScalaTest 测试源码，不改 lane、原证据或任何构建配置。使用仓库现有 AnyFlatSpec + ChiselScalatestTester 模式；测试目标是原 StrictFp32MatrixLane，而不是 Python LaneModel。

- 精确复用 strict_reference/STIMULI.json 的全部 52 个请求和顺序。实际 raw (a,b,acc) 去重为 41：前 20 个唯一输入 + 后 32 请求中的 24 个唯一输入 − 两组之间 3 个重叠。旧 SUMMARY.json 的 44 不符合该冻结文件；这里只核对计数，不断言旧计数错误的成因。旧摘要及历史 52 请求 / 99 trace calls 记录保持不变。
- 前 20 个期望逐字段校验冻结表；其余 32 个 signed-zero 期望来自仓库 Fraction 数学参考，不冒充官方 HardFloat 输出。
- 每条检查全部 15 个响应字段、每 pass 4 周期、双 pass 共 8 周期、fatal30 的 MulFatal 停止 Add、AddFatal 不提交、NX 非致命、UF 的 minnormal 交付边界、拒绝输入不产生合成 NV。
- 52 条有限输入响应分别保持 3 周期背压且持续给出不同竞争请求，检查响应字段稳定、禁止覆盖/重新接收。12 条 nonfinite 预拒绝、2 条保留 mode、1 条 legacy bad encoding 均检查立即响应后退休，不包含 3 周期保持。另有同周期退休与竞争请求测试，验证不接受 same-edge refill、无幽灵响应及后续新请求恢复。
- 8 个运算阶段及 held reply 共 9 个 reset 位置，检查 reset 立即屏蔽握手、无旧结果泄漏、后续新请求恢复。

执行过的限定检查：

    python -B candidates/qwen35_strict_lane_regression/generate_fixtures.py

该命令只进行 stdlib Fraction 计算、固定输入计数和 Scala fixture 逐字一致性校验；不加载 native ELF、不使用网络、不运行 Maven、不生成 pyc。--write 只重新生成本候选目录的 fixture。

未执行 Scala 编译、Chisel elaboration、Treadle/RTL 仿真或硬件测试。缺少测试后端依赖仍然是实际执行阻断。未来在依赖完整、经批准的既有测试环境中，把 source 下两份 Scala 作为 test sources，原 lane 和其 HardFloat/Gemmini 依赖作为 main sources，运行 heteronpu.experimental.StrictFp32MatrixLaneSpec。这里不新增下载或绕开原执行门的 runner。
