# 两项观察器诊断负结果：默认关闭，不接 DUT

结论：buffer没有可靠CPU收益证据，并实测削弱骤退尾部证据保留；selective LINE虽减少callback/frame次数，但作者和独立复核两轮fixture计时均更慢。两候选都不采纳到DUT，不提高原longrun预算，不继续追求positive结果。本包保留有限source/fixture资格和负结果，而非性能优化成功。

## Buffer

复用原writer纯stdlib闭包及原失败stream前120000帧，只比较原0、64KiB、1MiB缓冲与默认off四arm。对应storage write次数120001／171／12／120001，timed CPU约1.310727／1.247858／1.303903／1.375905秒。每arm一次固定顺序样本，不能证明稳定CPU改善或完整DUT加速。计时包含输入JSON decode、原JSON encode、生命周期审计、frame/raw/file hash与close，不包含DUT packet/result payload计算hash；digest字符串仅作为输入数据重放。

cross-mode记录字节与五个增量checkpoint相同，但accepted计数可能只存在RAM，persisted计数只代表已知OS确认前缀，不是fsync/power-loss durability。两个buffer arm的os._exit(73)负例仅留下8B header，丢失1214 accepted bytes；unbuffered未丢这些字节。这是失败证据保留的实质弱化，不能称崩溃语义等价。没有实际SIGKILL/signal、fsync failure或append内failed-drain覆盖。成功footer控制是合成一group序列，原真实prefix仍无END，不能升为DUT lifecycle或数值PASS。

35个独立声明case记录由1prepare＋4benchmark＋10negative×3组成；32期望exit0、3期望exit73。独审只读153文件／55651224 bytes及既有记录，不重跑计时。35是declared records，不是系统全局无其它执行证明。

## Selective LINE r4

三源码后像monitor/bridge/service_trace，显式opt-in才使用固定code→frozenset七点和per-code mask。op/consume/tick不订阅LINE，其余保留七观察点；callback先membership再取frame，不包原callback，不用DISABLE。原_return/context/capture/retirement与算术/调度正文不改，slot和foreign callback保全仍在。默认off与原路径一致。

有限AST owner/client fixture中M1/M2的十字段words/presence/frequency、writes、时钟、service/fold events和seal相同；端点为synthetic，不是正常source-loaded owner/Matrix runtime或真实Attention数值资格。计时用未插桩精确callback；另建Counter副本测调用次数，不能将Counter代码对象当生产runtime身份。M1 LINE117989→39232、getframe129747→13169；M2 LINE276991→87066、getframe306629→32957。调用次数减少不代表wall下降。

作者normal M1旧median约0.142s、新0.183s，M2旧0.329s、新0.413s；独立normal复核M1旧0.138s、新0.198s，M2旧0.329s、新0.417s。optimized同样退化，精确样本见两份timing/review投影。每arm交错3次仍只是小fixture样本，不能预测生产audit成本或完整DUT预算。

每mode unittest报告19顶层，其中1aggregate内又执行原26：18新逻辑＋26旧逻辑＝44 substantive identities，另1aggregate，45 executions/mode，两mode90。作者与独审各自重复这些身份，不得称180 unique tests。run01的KeyError来自计数fixture方法错误，不是DUT/field失败；r2计数叠加问题、r3慢版与r4仍慢结果均保留原hash，不改旧记录。

## 源码与复现

buffer writer/sink/patch和LINE三后像/patch保持原字节；两个harness仅将私有输入路径改为显式环境/JSON配置，公开source adapter尚未执行，原测量只绑定原harness。SOURCE_PROVENANCE逐项区分exact-copy与path-only适配，并保留原/新hash。没有新增算术、生产调度或全局缓存。

在独立fresh工作副本内，先提供已固定原stream本地路径及外部fixture闭包，不要在冻结证据目录执行。buffer复现命令：QWEN2_TRACE_SOURCE=LOCAL_TRACE python3.12 -I -B buffer/run_cases.py。LOCAL_TRACE须由调用方先opaque核原完整trace SHA9b821d7a5dc032b9c8f10232a96f51e639b2c6ad3cfaf8c2dccfe198c499e1b7；prefix身份为11089071B／SHA580343e92ade5f34e311c606f80887f5f8a103c2aebd3482022073ad6dad0fc6。此包不包含这些数据，也不下载或合成替代真实prefix。

LINE配置JSON需四个本地字符串字段：observer_root、owner_root、buffer_source、fullgraph_root，分别指向原test_observer包、原owner工作根（含replay_source及overlay结构）、原capture.py、原fullgraph候选根；它们不是任意替换为最新main的许可，需由调用方按既有source pins闭合原依赖。命令：QWEN2_LINE_INPUTS=LOCAL_CONFIG python3.12 -I -S -B line/run_bounded.py FRESH_OUTPUT。run_bounded会运行normal和-O两个受限子进程。两harness边界均每child1CPU／30CPU秒／45wall／256MiB AS，实际环境必须支持原CPython3.12 monitoring。改路径的公开后像未获得normalruntime资格；本包不伪称自包含fixture或DUT。

这些是供受控复现的精确接口，不代表本次重新运行：打包期间没有测试、target import、native、DUT或oracle读取。原55MB产物、rawtrace/二进制、privatepaths、地址/PID和APPROVAL不上传。原失败与所有旧pins不改；固定4096 MAC及legacyPV63.57%上界保持，无80/90%、cycle、频率或RTL结论。
