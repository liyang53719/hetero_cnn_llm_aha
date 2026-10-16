# 原始 Public PV16 M128 paired-reference linked launch

## 中文计划
- 已完成：独立 native16/128 数值通过及精确 AVX512-BF16 dispatch 实例证据；runtime 接线冷测试通过。
- 已完成：最终 linked SETUP+ASSETS admission、十二个严格生成源码身份及73项冷测试 normal/-O（8.183/8.767秒）。实际 source-only composition 校验283个源码身份，禁止数值包和 native 加载。
- 已记录：原始 Public M128 run38952336951 数值包络超时，无最终数值PASS；历史安全证据单独归档。
- 进行中：源绑定、原子有界的子阶段/Host事件诊断及独立审查。
- 待完成：根据诊断能力和资源预算审查下一次数值尝试；尚未重跑，没有继承历史全链路PASS。

本层保留原始 Public owners/Matrix/Host 和两个 C++ hardware references。producer/admission 的 runtime import 绑定最终source contract；原有三个控制入口绑定身份与安全backend diagnostic dispatch。2026-10-16又在最终entry加入固定阶段标记及原trace事件的只读旁观，所有算术、原始数值阈值及gate不变。

一份 fresh setup 同时绑定双 recipe ELF/receipt、generated gate、native16→128 prerequisite、全部原始 exports 和严格完整九条 avx512_core_bf16 BF16 matmul；观察到 AMX 或未知 dispatch 会在 Public 计算前失败。CPU flags 不能替代实际 primitive 资格。

工作预算：900秒 setup、2400秒内部 Public、2430秒外部数值阶段、3420秒绝对总期限；整个 job 60分钟。仅 workflow 自身路径 push 或 manual 触发，run_attempt=1。最多两个顺序 VM placements：只有第一个在 clone/setup 前经严格校验的 CPU_UNSUITABLE 才能启用第二个；最多一个 setup/Public 数值尝试，其它失败立即终止。第二个仍不合格则整个 workflow 失败。输出只允许三个固定安全 JSON，权重、数组、完整私有日志不上传。

原始运行已进入numeric后超时；本次新增诊断代码尚未执行新的setup/native/Public。

## CPU placement 修正
实际 run38949728447 在 environment backend gate 拒绝，耗时49.381202秒，cpu_avx512=false，未进入 Public。修正仅加入下载前的必要硬件资格筛选：所有 processor 记录都须有原 AVX512 flags 与 avx512_bf16；任一 processor 出现 amx_tile/amx_bf16/amx_int8 时保守视为本 profile 的 placement 不合格。它不是 Torch dispatch 或数值等价证明，不设置任何 ISA override。缺失/损坏 cpuinfo、override、超时、source/Git 错误均不是可换 VM 的 CPU_UNSUITABLE。

后续仍必须通过原 Torch backend gate 和 fresh native16/128 各九条实际 avx512_core_bf16 dispatch。packages/编译/native/Public 失败均不重试。早期拒绝也保留固定 summary/progress/source_hashes；所有 started 标志必须为 false 才能换 placement。当前变更仅冷测试，未执行新的 setup/Public。

CPU placement 修正冷测试：runner49项 normal/-O通过；linked完整82项 normal/-O通过（8.058/8.290秒）。包含混合processor、AMX union、malformed/late资格失败、精确source/Git/receipt负例及setup/native失败不换VM。

## 2026-10-16 原始 Public M128 超时与诊断修正

run38952336951 / job117146548710 / commit ac3a074cd0e29342447844a7675425af628a39ef 在 numeric 阶段 TIMEOUT；wrapper 总耗时2587.336054秒，未完成 postflight、没有 Public 数值 PASS。三份安全 JSON 只保留外层阶段。run_ci→setup.run_group 的 traceback 是父进程 proc.wait(timeout)，不能定位 Attention、FFN 或比较阶段。numeric_started 与绑定源码顺序只支持 setup 已返回 COMPLETE_FRESH_SETUP 的推论，不能替代未上传的 native 私有数值receipt。

预算保持900/2400/2430/3420秒。2430秒数值包络预留5秒cleanup与1秒receipt，子进程等待约2424秒；admission、prepare、source检查、实际执行、比较与postflight共用此包络。内部2400秒只从后面的实际执行计时开始，名义余量约24秒。旧1548.112秒结果是不同commit、116源闭包，14个重叠源码不同；另一份synthetic Attention性能也不能转成此运行的完成证明。

新增 numeric_progress.py 仅写固定私有文件，最大4096字节、最多256次原子快照。独占writer claim、context/source SHA256、sequence、单调elapsed和phase elapsed绑定本次运行；RETURNED仅表示该Python阶段返回，不表示任何数值gate通过。elapsed从数值诊断writer创建时计时（首次context校验之后），不是wrapper总时间。阶段覆盖setup admission、import、snapshot preparation/bind、执行、验证和postflight；原始入口额外标记input load、prefix、suffix、observation seal、comparison、source recheck和receipt。

原始 Host/owners/Matrix 源码完全不改，保持既有三变体兼容约束。入口只旁观既有私有trace.event：原事件原对象先交原sink，不改变clock、请求、响应、内存或算术；旁观者只提取已接受Host事件的固定operator、原request tag低16位/原completion PC、5项整数计数。原trace、请求对象、地址、数组和权重均不进入诊断JSON。没有逐tick hook、数组trace或推测的MAC计数。计数为软件Host事件，不是RTL周期或硬件利用率。最后一次事件可能早于超时；其elapsed不能解释为精确停止时间。

父进程清理超时子进程后可独立校验并把最后完整快照投影到失败summary，不依赖numeric.validated或postflight。缺失、未知字段、非法枚举、非有限数、超限、旧context/writer、损坏/半写文件均不成为数值凭证；summary只标numeric_progress_unavailable，原错误仍保留。进度从不覆盖frozen metadata/source proof或existing acceptance receipt，不允许status=PASS。成功仍仅沿原严格numeric.complete验证路径；上传依旧是summary/progress/source_hashes三文件，workflow不改、不触发数值重跑。

本次仅冷测试及source composition；精确源闭包增加到285，生成文件仍12。另见同级raw_kv_public_recipe_timeout的历史失败证据；不会用新增诊断反推旧run内部阶段。当前待独立审查，尚未执行新Public或RTL。

安全保证边界：父进程只校验一份当前context/source/writer绑定的完整快照；更新历史的单调性由源绑定Writer检查，不能从单份JSON独立重建。它不是抗同目录恶意篡改的密码学日志。诊断写失败会fail-closed终止执行，不是静默best-effort。新增原始CappedTrace/jsonable源码hash绑定的冷回归，确认77个合成事件的原trace字节/哈希/计数及截断行为完全一致，原sink返回值/异常保持；这些是CONTROL_ONLY事件，不是数值运行。
