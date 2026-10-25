# M2 Attention 三臂 selective 诊断：有限实际结果，不采用

本包仅新增精确源码副本、逻辑 pins 与脱敏证据，不接入完整 DUT，不改变默认监测路径。唯一实际运行按 off、original、selective_r4 固定顺序执行 M2 Attention；原 parent 为 exit 0、无超时、进程组清理结束，wall 6.23116281197872 秒，worker process CPU 6.150630126 秒。实际独审的范围与原始证据身份见 evidence/EXECUTION_REVIEW_PROJECTION.json；这不是完整 block、M128、RTL 或性能验收。既有完整 M128 CPU 超限 FAIL 不变。

## 计时只作诊断

三臂 owner-through-terminal-ACK-and-monitor-exit 的 process CPU 分别为 0.168004826、0.589193066、0.563943544 秒。一组固定顺序受缓存、热身和先后影响，不能据此报告稳定加速、因果 callback-only 成本或采用结论。off 仍保留必需服务事件观测，并非零监测基准。clean 计时没有 count probe、profiler 或 callback wrapper。

公共 driver 区间在 monitor 安装和 installed-mask 检查之后开始，包含原 driver 与真实退出实现；off/original 使用原 ExitStack，selective 使用原 R4 bridge.observe_driver，因此不是只改变 callback 数量的因果对照。额外 post-exit mask/state 验证单列为 post_timing_monitor_lifecycle_validation；setup/source hash、字段封存、artifact I/O、臂间审计和 reference 分开计时。源记录的零 CPU 分辨率值不代表零成本，嵌套阶段不能任意相加。

历史 R4 synthetic fixture 仍为 selective 更慢；其原 timing summary 单独保留，不与本次 M2 混成一组样本，也不重跑来替换历史。候选继续 default-off、不采用。Python 时间不转换为硬件周期、有效 MAC、80%/90% 或 M128 预测。

## 真实运行范围与证据边界

三臂均用原地址映射 qr/kr/v、原 Matrix/Scalar service、已有 native combined ELF、strict ordered lanes，以及实际 owner terminal ACK 与资源释放。Scalar BF 每臂 19968 次、native_fmas 933888 是此 M2 组件运行计数，不是完整 block/M128 或硬件利用率。原完整 ServiceTrace 包围所有臂；原始服务事件、三份 output/score/write、两组十字段与 presence/frequency 均保留在私有执行产物中，不随本包上传。

运行内原 comparator 检查三臂 output/score/write 与计数、完整生命周期控制等价；ticket 只在跨臂比较时按首次出现双射规范化，原事件保留。两个 observer 的十字段对照，以及既有独立 AST recipe 的三份 output/score 和两组十字段对照，均限定为原记录实际完成的检查。reference 在全部三次 terminal ACK/release 及控制比较之后执行；其源码预检以及共享精确 RNE primitives 的提前加载如实保留，不声称 preterminal 完全没有 reference 源字节读取，也不等同官方完整 Transformers forward。未来 padding/sentinel 不是观察到的有效值。

selective 的 capture/monitor/service_trace/bridge 完整模块正常加载，绑定原 R4 source hashes，ast_definition_test=false；敏感 _line/_return 没有被包装或替代。实际 installed/cleaned mask 验证与绑定结果保留，但公共 role_code_identity 只留源码相对位置，物理路径不公开。module/maps 检查只是相应边界快照，不是完整 OS 访问事件历史。

独立实际审查完成 22101 项检查、零错误，重验 1026 pins；每臂完整生命周期为 1515 events、216 tickets，三臂原 ticket 范围依次 1–216、217–432、433–648，仅比较时做双射。审查按留存 bytes/hash 检查三臂与 reference 的 output/score，以及两 observer 与 reference 的十字段 values/presence/shape。两个 observer 的 frequency 相等，但 reference normalizer collector 重复 8/16 次而 DUT 每值观察一次：值与 presence 一致，不声称 reference observation frequency 相等。DUT report 的 writes 指 unique first writes，reference 的 writes 指全部 collector events，不能直接当相同口径。审查最初误认 frequency 为 u32，已按源中 u16 格式与上述计数语义修正；初始审查错误记录保留，target evidence 未改动。

原 launcher 只有 RESULT/PARENT 等产物，没有独立最终 receipt/seal；后补包外 115 artifacts / 4222415 bytes 的 hashes 是独立保全证据，不追认成运行原生 seal。本包的 public projection hashes 与原 receipt hashes 是两个身份；不把 hash 相等或独审读取称为重新执行数值参考。1 GiB 是 AS 限额，不是 peak RSS 实测。无新 native/model/mock/cold/benchmark 运行。

## 源码、测试与历史身份

19 个 Python 文件逐字复制：13 个原 executable manifest 文件、1 个准备 mock 测试，以及 reused 下 4 个 R4 模块和 ProjectCodeGate helper。manifest 中的 cold_import.py 是继承接口，不表示本次额外执行过 cold import。公开复制位置不是新的执行配置；没有 path adapter，也不把副本移动当成新运行资格。

1026 条原 source/runtime/input pins 按原顺序、重复、bytes/hash 逐条保留，仅转换为逻辑角色；其中包含 316 个 assembled-source 记录。完整 assembled source、外部原测试闭包、Python/NumPy、已有 native ELF 与私有输入仍须另供，包并不自包含。禁止把逻辑 pins 当可执行 PRIVATE_CONFIG。

历史准备 mock 是每模式 28+14+22 = 64 个逻辑测试，normal/-O 共 128 次执行；独审重跑同一身份不是新增 128 个 unique tests。r1 installed-mask 故障导致终止路径问题的 BLOCKED 留存；r2 在非取消故障时先记录 capture_error，再让原 driver 完成 terminal ACK/release，最后拒绝验收。两项 exact drive AST/fake-owner 控制测试不是 native 算术证明；KeyboardInterrupt 仍为取消。准备阶段 review 中“actual 未运行”的措辞是历史状态，不能覆盖后续唯一实际运行记录。

实际入口仍是 launch.py --config LOCAL_CONFIG --review LOCAL_REVIEW --review-sha EXACT_REVIEW_SHA --approval LOCAL_APPROVAL --approval-sha EXACT_APPROVAL_SHA --m 2 --output FRESH_OUTPUT。这只是接口说明，不是新调用或授权；旧一次性审批及 attempts ledger 不可复用。原资源限额为 1 CPU、30 CPU 秒、45 wall 秒、1 GiB AS。不得自动重试、增加预算或重启 M128。固定 4096 MAC、legacy PV 63.57% 上界及完整 RTL/90% 目标均未在此片验收。
