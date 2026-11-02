# 2026-11-02：真实 4096 MAC / 原 P0 首 fault 两槽观测已闭合，尚未修复

- 原唯一 `cloud_execution_p0_first_fault_connectfix_20261102T1635` / session 44518 已退出 2；新 executor 1a50、实际 artifact 7a99 / ELF b89a / 原同字节 SV 3d148 / 只读 driver abed。九个前置阶段严格 0，包括 fresh ABI 与真实完整 connect；随后单 P0 DUT 因 `resetRequired` 退出 1，outer native 2 / errors[] / strict cleanup / EOF。P0 阶段耗时 6036.663 秒，sampled RSS 248,307,712 B；不是 10800 秒墙时或 1,500,000 active cycles 上限耗尽，采样 RSS 不冒连续峰值保证。
- 原完整 `summarize_cloud_execution.project` 经过真实 source、七件编译 proof、retained、原 DUT evidence 与 acceptance 门，重聚合为 VERIFIED_REAGGREGATED；摘要 SHA 18d9c23c5ceff666d416b811c83b02023b68e9bd63ae7359a6fea8a35c8823d2。只选 P0，其余四块 NOT_SELECTED；完整数值及 final RTL 资格仍 false，不将本诊断当五块验收。
- 114 字段固定 schema 的三行只读记录为 PRESENT_VALID，原 profile0.log 全字节投影时 SHA 65692f6a36cdbfa9d97dd051bac6342ad6570b858ec78cc5fcf40ee73e05fcb1。上一健康槽 cycle 852611 / active 852606，到首 fault 槽 cycle 852612 / active 852607，均完成 1 条命令；Matrix wideSteps 为 12800，DownOwner 原窗口 ng 投影为 160。ng/status 不是有效窗口完成凭证，任何 payload 位仍必须带其 valid 限定。
- 首变包含 DownOwner status 0→8 与 reset 0→1；原 Protocol.scala 明确 Numerical=8、Protocol=7。Matrix 已观察 poison/outputBad/endpointError/completionBad/seed reset 位在两槽为 0；Guard ownedAuthorityFault 与 Top physical/ordinaryAdmission 同拍升高，原接线存在下游反射路径，不将多个同拍 bit 当多个独立首因。独立源码可达性审查进一步排除另外两个 Numerical 路径：drainActive 会使 result.ready=0，与前健康槽实际 ready=1 冲突；真实 ng160/K[0,1024) 的终端读取必须等最后 half 良好 DDR 响应完成，其后 outstanding 已清、nextLoadK=end 禁止新 prefetch，window 不进入 prefix restore，因而终端返回时 sourceFinite 的 burstResponse.fire 不可成立。结合前拍 context0 result.fire/status0 与下一拍 status8，可作“源码不变量推导定位”：DownOwner 终端 context0 返回的 finite 门失败。实际 FP32 Kwindow 不启用 BF16 物化阈值，M128 检查全部 16×256 返回字，因此推导至少一字非 finite。不是直接采到 finite 位或数值 payload；坏 lane、NaN/Inf 分类、有效输出还是 padding、具体算术/存储来源仍未知，不宣布底层根因已查明或修复。
- 新已闭 n0 局部输出 128×1536 / 786432 B，与官方 BF16 input_layernorm 按 uint16<<16 展开为 FP32 storage 逐 196608 word 全 bit 相等，SHA ddee5fd75094777c51ef1104c7a18dfe527fef9de2a24646aad1d83160a6e421，0 差、无 nonfinite。只证明该已完成 norm 局部，不能推出后续 Dense、整块 y/K/V 或其余内部 gate 已通过。
- 本批只发布无本机路径的有限闭态/控制观测证据与计划，不含 raw log、tensor、权重、ELF、额外 artifact，不改变硬件、驱动、资源门、catalog 或 nonce；不自动重跑、不再追加 mock 层、不盲目扩预算。原失败/完整七件与所有闭回执保留，下一步在这些真实观测基础上收束 Numerical 的有效触发来源。

---

# 2026-11-02：实际新 ELF 已过 ABI，P0 connect 新 schema 路由恢复

- 原唯一 `cloud_execution_p0_first_fault_20261102T1538` 入口已严格退出 1。实际 8 个前置阶段 native 0 / errors[] / cleanup EOF（archives、三 runtime、startup ABI、P0 initialize/provider/transport），P0 connect native 1 / errors[] / cleanup EOF，收据 b5d4147e51f7619d10926c3a801338f9762cc539499fddd5da6c73984f355b49。DUT 数值模型未启动；不能说新 ELF 完全未执行，fresh ABI 已实际执行。
- 原闭合 2042 B 日志及 raw/gzip SHA 全留存。准确拒绝点为 `connect_owned.preflight` 只识别旧 FIVE_PROFILE artifact，导致新 FIRST_FAULT artifact 未带独立 source_relocation 进入原 `artifact_identity` 而被拒。`connect` 本体存在相同分支，需一并修复，不能只跨过第一门再重复入口。
- 本批只将这两个 selector 显式扩为两个已审 artifact schema。必须先调用原 `approved_source_relocation` 再使用原 identity/driver/ABI/proof 门；不削弱任何独立审批、P0-only、原刺激、source/hash 或数值校验。测试应覆盖实际 `preflight→connect→load_binding` 调用链，而非只直接调用底层 load_binding。
- 完整实际调用链离线回归 R3 已严格 native 0 / errors[] / cleanup EOF，20.731 秒，sampled RSS 126,636,032 B；原回执 SHA 0a51adf97f400738b234059e07cd7ab4c9c1a332184cfd03679841aafde47e93。同一真实七件/参考/程序及全部生产 validators 下，旧 preflight 与旧 connect 完整函数均按原错误拒，新 preflight→connect→consumer.main --validate-only 通过。只有离线 source/owner 的 proc/time 与 ABI authority/cache metadata 是明确 synthetic；历史实际 ABI 原字节保留，不能称新 ABI 或 DUT PASS。R1 缺 fixture mode 拒、R2 材料错放 stage 内触原 symlink 门均保留；R3 使用生产同构 sibling material 全 watch，512 MiB 只约束阶段 run/log，材料受原 aggregate TREE/file/entries/disk 门，不改监督器。
- 实际 7a99 artifact / b89a ELF / 3d148 SV / abed driver 保持不变；仅 host-only source CI 与新 executor 适配，不另建硬件、不重复传递。所有旧失败、原闭回执及前次纯联测范围保留。新 source 正式输入仍须新的实际身份/adapter/resource 与 fresh 原门，旧 runtime/ABI 资格不得偷迁。
- 本地 UTC+08 2026-11-03 的唯一受审 24-file 保全批已严格闭合：21 gzip 完整解压 SHA 核验、3 原 SV 同字节 hardlink，归档 80,044,807 B，实际释放 1,818,570,752 B；原结果/日志/输入及所有唯一字节均保留或可完整恢复。本日不再追加清理。此前原入口实际 upfront 磁盘门通过，后续仍以新身份实际重核，不继承余量快照。
- 完整调用链读域复核另发现：旧 1538 adapter 实际读取 builder 的 SOURCE_PINS 小 metadata，而原 watched roots 未覆盖该旧 E 父域。保留这一覆盖遗漏，不追认旧资源清单完整；下一正式 control 将原 b029 catalog 原字节副本置于实际 watched control，并同步 adapter pin / 独立 review，不以扩大无关根目录凑磁盘。
- 单 P0 原 10800 秒 / 1,500,000 active cycles / 整轮 22200 秒工程诊断预算不变，不是完成预测；原 RSS 2 GiB、AS 2.5 GiB、未知 owner 5 GiB、非 DUT 1 GiB、TREE 与 8 GiB 磁盘 reserve 不降。完整数值仍 0/5 INCOMPLETE，故障原因尚未由新只读记录定位。

---

# 2026-11-02：实际首 fault 七件接收与执行前 catalog 形状兼容恢复

## 已闭合的真实构建与传递
- 唯一 run 41454910027 已 SUCCESS，20 个真实原阶段收据均 strict native 0，七件唯一接收并完整编译/依赖 proof 通过。ZIP 311,448,009 B，SHA256 8252ada74983e1eaddcef77c52b943f7d0fe1d6e88fe829fc917fd37ab4a8385。
- 新 manifest 7a99c2c8bbc0df2f2b63c14d8163c13b3923aea41c28181661016f7a4540d24c；新 ELF b89a701b262e7edb575b19d03a058fc37ae10030ecce040a4895d6a9e143ebe0。同源 SV 精确保持 3d148277…，只读 driver 精确为 abedbe2a…；实际 159 硬件源、4096 MAC、单 32-lane bank、122 端口不变。
- 实际 114 个只读 probe mappings、root header/accessor/config、全部 16 个唯一依赖均核。此次真实 `.d` 有 17 个词，Top header 同词两次；这证明本次新处理保留完整依赖，不追认前次未取得的 `.d` 具体子因。

## 当前阻塞及本批边界
- 新实际 candidate review、DATA/reference 源与独立工程 watchdog 已形成；完整执行前 adapter/handoff 门在 catalog schema 拒绝，尚未到资源 census，未执行新 ELF。真实 builder b029 catalog 是 exact `{schema,files}`，旧 adapter 只接受带 `original_source_commit` 的三字段形状。不得修改已构建七件或给旧 catalog 补字段偷换身份。
- 本批仅 host-only adapter 支持两个明确 exact 形状；旧三字段若存在仍严格 40 位十六进制，未知字段仍拒。builder/executor commit、独立 catalog SHA、全部实际文件/完整差异白名单及 review 身份门不变，不将缺字段视为省略身份验证。补真实新七件 adapter→handoff 全链，而不只测试单个 schema 常量。
- 本批不触硬件、SV、driver、C 构建代码、运行预算、nonce 或 workflow；只源码提交和 source CI，不重建、不重复下载。实际执行继续使用新 b89a ELF，但必须通过新 executor 适配、完整实际 handoff、资源/磁盘准入和 fresh ABI。
- 原单 P0 工程诊断上限 10800 秒 / 1,500,000 active cycles，整轮 22200 秒，不是完成预测；旧 1935 五块结果仅历史依据，不迁移为新 ELF 校准或数值通过。原 RSS/AS、未知 owner 5 GiB、非 DUT 1 GiB、8 GiB 磁盘 reserve 和 aggregate TREE 门不降低。
- 当前完整数值仍 0/5 INCOMPLETE；新构建成功不等于 P0 fault 原因已定位，也不等于新数值验收。

---

# 2026-11-02：首故障构建后处理的依赖规则兼容恢复

- 原唯一 build run 41441028806 已失败：Actions 有限投影显示 20 个阶段直到 host_link 均 native 0、无监督错误、cleanup/EOF/gzip 完整；随后原 GCC .d 解析器在“非空、原 token 唯一、≤4096”合并谓词拒绝。七件上传被跳过，实际 artifacts 数为 0，没有可继承的新 ELF 验收，也没有新 P0 执行。保留完整本地日志和有限阶段证据；有限投影不是已下载的原 worker 收据。
- 原远端 .d 未取得，所以具体失败子条件及重复路径仍未知。已有严格闭合 tiny GCC 产物和新的真实 GCC 小预处理证明完全相同 prerequisite 可以合法重复；这只是确定的解析兼容性缺口，不等同原 P0 resetRequired 因果已找到。
- 本批仅在显式 first-fault readonly candidate 域新增版本化 capture/parser。原 .d 全文及 SHA 保留，原 1 MiB 文本和 4096 原词上界先执行，只稳定折叠完全相同词；多规则、非纯路径、父级遍历、不同词归一碰撞仍拒绝。全部唯一实际依赖仍逐原 pin 核验，driver/sparse/observer/root/accessor/helper 与五编译阶段 strict 门不删。旧 P collector、旧 C parser、旧 artifact 实现锁不改，旧实际七件用新 checker 的完整编译证明仍通过。
- 新依赖记录显式 GCC_MMD_EXACT_REPEATED_PREREQUISITES_V1；新 artifact 必须选择新 capture/验证语义并报告真实 collector 源 SHA，旧 artifact 拒绝携带新 policy。失败诊断仅固定原因枚举和词计数，不透出原始路径/日志。硬件、159 源、122 IO、driver、只读信号 schema/config/算法和原预算均不变。
- 受监督完整夹具 R3 已严格退出 0：实际 Python producer.run/prepare/完整 pins → 新 capture → pack/full proof → 真实 exporter CLI → 精确七件目录；真实原诊断 driver 仅执行 GCC -E/-MMD，原始 16 token/15 唯一依赖，全文和完整 15 pin 不丢。12 项拒绝反例均通过，并恢复最终完整 proof。五构建阶段、ELF、身份/收据明确 synthetic，未编译或运行 DUT，不能冒充真实新二进制资格。独立审查已核原监督回执、日志、依赖 pins、export 七件。
- 此夹具沿 879 源快照执行，与最终 nonce/测试/有限证据包装分开记账。此前两次夹具因合成 Make 目录和缺传递 header 被原门拒绝，现场保留；修的是夹具输入闭包，不是放宽产品校验。原输入/SV 未改，只有成功轮一次有界 SV 复制。
- 接续只允许完成源码审查/CI 后，以新独立 nonce 启动一次同约束完整构建；不从已失败 run 迁移 ELF PASS，不加第八件，不上传原始日志/权重/参考数据。实际新七件仍须完整证明、独立 review、ABI、资源与磁盘门之后，才可按前述 10800 秒/1500000 cycles 单 P0 诊断提案执行。整体数值目标仍 0/5，禁止把格式小例或协议 B 当数值完成。

以下完整保留此前主计划正文：

# 2026-11-02：P0 首故障只读诊断的宿主执行接线（非执行批准）

## 当前事实与本批范围
- 唯一完整硬件构建仍沿源码 `e1efd05fbd682405dffd090e278e69897f80e2f1`、激活 `f9d2c05cc66856278cebc02c43d122dfd1f01089`、run `41441028806` 执行。本批不改该 builder，不新建 launch/nonce，不重复构建，不改 159 硬件源、4096 MAC、122 IO 或 driver。
- 本批仅宿主 E/N/runtime/controller/summary 与对应精确测试及有限纯链证据：新 `P0_FIRST_FAULT_DIAGNOSTIC` 明确只选 P0，P1–P4 为 NOT_SELECTED；注册的五块完整硬件定义及旧 CALIBRATION/STAGE/FULL 分支不变。新 scope/status 与旧数值评估域分开，诊断输出不证明首因或数值通过。
- 预算提案为 P0 原完整 M128 刺激 10800 秒 / 1500000 active cycles，whole 22200 秒 = 材料预留 6090 + 保守 tail 15510 + 入口余量 600；这是工程上限，不是完成预测或新 ELF 实测校准。新只读探针开销未知；实际新七件、独立结构/driver 关系审查、ABI/资源/磁盘门及正式批准尚须逐项完成后才能启动。
- 纯 provider 复用新增严格版本分支：旧 V1 同 artifact 门保留；新分支逐审旧 driver 343e、诊断 driver 逆剥、同固定 raw SV、原 program/输入/转换契约及旧闭合来源，所有实际 authority metadata 目录纳入监控。不把不同 ELF 当相同执行资格，不省略 fresh runtime/连接/ABI/输出隔离。
- 受监督纯链 R2 已严格闭合：真实 C pack/七件完整 proof、N/E 准入、原 retained 完整哈希与原 evidence/acceptance/summary 均执行；ELF、身份/授权及运行收据明确为 synthetic，未执行 DUT。正例只得 VERIFIED_REAGGREGATED/PRESENT_VALID；额外 P1、缺 doc 拒绝，坏 snapshot 为 MALFORMED，全部 numerical_pass=false。该测试使用当时 874 源快照，不能冒本批新执行资格。
- 独审另抓到真实 controller 最终 FLOW_RESULT 写旧 scope 的缺口；本批仅为新 mode 修精确 scope，并以唯一生产 save 表达式真实落盘、再走原 summary scope 门测试。旧 scope 分支保留；该补测与此前纯链分开记录，不声称旧纯链已覆盖该写出点。
- 最终 builder→executor 全差异须精确 allowlist 与完整源 catalog 校验。本批只发布源代码及有限证据，不上传原始日志、SV/ELF 或数据，不扩大原七件传递范围。原五块仍 0/5 完整数值验收；局部 norm 相等、B 协议通过及工具小例均不得升级为原 P0 故障已修复。

以下完整保留此前主计划正文：

# 2026-11-02：原完整硬件 P0 首故障只读观测（源码／构建准备，尚无新数值结果）

## 当前事实与边界

- 原完整 4096 MAC、共享 32-lane 向量 bank、五块 M=128 实际长窗已全部严格收尾；完整数值仍为 **0/5，INCOMPLETE**。五块首个 input norm 局部产物均逐 bit 等于官方参考，不等于整块通过。P0 在首 matrix 期间 `resetRequired`，另外四块在 1,500,000 active cycles 上限结束。
- 单独云端 B 协议诊断原 run **41429101257** 的 11 个阶段均以原严格门闭合。真实 Router／Coordinator／Bridge／DownOwner／banks 走过首个完整 N 窗及第二 N 窗第一 partial 终态；Matrix、vector、DDR 响应仍为明确的协议替身。它未复现原 P0 故障、未证明真实矩阵算术。
- B 首轮 tick 62002 的异常与测试驱动在更新 mock valid 前采样组合错误的路径一致；真实 Bridge 三场景小对照验证该风险，修正驱动顺序后 B 实际跨过此点并完成上述协议边界；原实际生产 driver 本就先驱动再采样，因此不能将该修复迁作原 P0 根因。B 的 dst 取 manifest 的 `q`（4485895360），原 pc1 是 `qraw`（4484322368）；B 不是原完整命令重放。原 P0 没有可供比较的 qraw partial 文件，写 ACK 字节计数不能冒充数值产物。

## 最窄新增观测，保持行为与硬件定义

- 原 Scala、159 源选择、GENERATION_CONTRACT、HIGH／LOW／SV 生成算法及 122 个顶层端口不变；原 driver `343e9978…` 文件完整保留。旁置新 `host_axi_driver_first_fault.cpp` 仅有三处显式插入，固定逆剥验证必须逐字恢复原 driver 全文。
- 使用独立、精确模块／变量名的 Verilator `public_flat_rd` 配置，仅读取非 hierarchical 的 Top／Owner Kernel／Matrix service／runtime guard 的 114 个控制标量（327 bit）。不开放全局 public，不增加顶层 IO，不使用 VPI/DPI，不穿透三处原 hierarchical 边界，不导出数据、权重、参考张量或地址。
- 原 `clock=0 → 驱动 AXI 输入 → eval → need(!resetRequired)` 顺序和原拒绝语句不动。在同一检查点只读采样宿主两槽（上一健康样本、当前故障样本），仅失败时一次输出固定 schema 与 indexed 控制数字。没有额外 eval、时钟边沿、输入写入、数值替换或正常路径日志。裸组合位必须结合固定有效条件解读；快照本身不自动证明唯一首因。
- 原实际 SV 的完整 SHA256 `3d148277114ff5d968d0e200f4ab117839a3b6c0c0d33e5388e6e5268d42d029` 是新产物严格条件；不以删除注释／路径归一化掩盖差异。实际 frontend 后、Make 前须按生成 root header 的唯一名称／声明／位宽生成只读 accessor，缺项或歧义直接拒绝，不填零。实际 GCC 依赖及原 20 阶段／5 编译阶段证明继续核验。

## 已有局部证据，不替代真实新构建

- 实际 hierarchical tiny 工具验证确认：子模块 public 变量虽保留，但 Top 仅有 opaque protectlib handle，不能经公开生成对象接口读取；该路线已停止，未通过 cast、getter 或去除层级绕过。
- 同一 tiny SV 的 baseline 与 exact Top public 配置分别完成原工具生成、make、link、native 六阶段。11 行功能输出逐字相同；故障检查点 eval=10／rising=4，正常 eval=12／rising=5，无新增边沿或 eval。这里只证明非 hierarchical 只读访问及检查时序，不是原 P0 的硬件复现。
- 原宿主 collector 的独立 C++ 测试在合成 accessor 下验证无历史、两槽、只打印一次和所有位宽最大值；最大输出 1010 B，小于 8 KiB。实际硬件 accessor 尚待本次新构建，不能以 stub 资格代替。
- 新分支已有真实 pack → checkout-local 七件入口 → 完整 compilation／readonly proof 的 normal／`-O` 端到端测试，5 类错配反例均拒绝。源角色、driver 逆剥和原 SV 字节真实；ELF、编译收据、生成 header 和依赖元数据明确为合成夹具，不授予实际编译或执行资格。旧真实七件也在新 checker 下完整复核通过。
- workflow／guard／prepare 的真实临时 Git 身份链及显式只读 selector 已联测；bootstrap／materializer 的精确原 parser／argv／selector 语句与固定 policy 连接已测，完整工具 inventory 未在轻测中执行。缺旧上下文和初次测试维护失败记录全部保留，不冒初次全绿。

## 新身份、构建与后续单 P0 执行

- 新配置、accessor、driver 和 ELF 均为新身份，必须使用独立 FIRST_FAULT 产物／review／source evidence 合同；硬件旧 generation 与新 driver 是两个明确域。旧 CAL／STAGE／FULL 数值准入不因同源关系自动授权新 ELF，旧结果不迁为新数值通过。
- 本次仅按原 full build 的预算与原七文件类别构建一次；七件仍为模拟可执行文件、同源 SV、driver 源及四份原类别清单／收据，不新增第八件，不上传本地原始日志、权重或参考数据。源码 CI 成功后才以独立精确 nonce 唯一启动；不并行重复 full build。
- 新七件下载后须严格校验、实际 source／结构／只读证据独审、fresh runtime／ABI 与新执行输入资源审查。运行接线若随后以 host-only 源提交完善，须明确 builder／executor 差异和全量 exact allowlist，不重编同一硬件、也不省略适配门。
- 拟单 P0 `P0_FIRST_FAULT_DIAGNOSTIC` 仍使用原完整 M=128 程序、输入和原数值门；P1–4 明确 NOT_SELECTED，不伪造五块启动。工程 watchdog 为 10800 s／1,500,000 active cycles，whole 上界 22200 s（6 小时 10 分）= 6090 材料预留 + 15510 保守尾段 + 600 入口余量，**不是完成时间预测或 FULL 预算**。新 public 配置及 114 项宿主读取的实际成本未知；旧 1935 长窗只作历史故障时点／工程上界依据，不冒新 ELF 实测校准。
- 最终实际资源、watched roots、磁盘／内存门和新批准输入在新七件就绪后重新核验；保留未知旧 owner 5 GiB 与非 DUT 1 GiB 预约、原 8 GiB 磁盘门及严格 cleanup。未实际通过这些门前不启动 DUT。主目标仍是解释原故障并推进五块完整官方参考比较，不无限重复诊断。

---

## 2026-11-02 10:23 UTC：B 已运行到协议；纠正 mock 驱动与采样顺序

- 原唯一 run `41423897669` 已关闭。全部准备、compile、emit、ports、Verilator、make 均 strict0；emit 114.7673 s / sampled RSS 2,191,253,504 B，Verilator 101.2595 s / 2,296,471,552 B，make 705.9808 s / 2,814,488,576 B。协议模型真实启动，native1 / errors=[] / cleanup+EOF+gzip 完整，172.4364 s / sampled RSS 186,236,928 B。不是资源 cap、入口身份或 TargetDir 失败。
- 有限闭日志记录 ng0 两个 K partial 在 tick 52374 / 61992 正常 terminal，captured=5、written=5、status=0。随后 tick62002 reset=true，但 owner state/status/firstStatus=0、bankReset/firstBankReset=false；未到 ng160。此反例不能直接等同原 P0 resetRequired 首因。
- 三方源码核查发现确定的 fixture delta-cycle 风险：旧循环先读取 reset，才根据上个 edge 后更新的 mock 状态刷新 vector.result.valid。真实 Bridge 结果已 fire 使 inflight=false 时，旧 mock valid 在下一次 poke 前仍 true，触发组合 unexpected→tiles.abort；真实 DownOwner 将该 abort 组合反映为 resetRequired。该边沿间观察不等于被时钟采样的硬件错误。
- 已用原真实 DenseTileSumBridge 小模型实证三场景，未改生产：旧顺序的 stale unexpected/tile_abort 真而注册 reset 假；先驱动再采样并跨 edge 保持健康；非法 valid 真正保持跨 edge 必须触发 sticky reset。compile 13.1274 s / 295,612,416 B，model 12.8352 s / 452,612,096 B，全部 strict0。小模型无真实 banks，不冒完整 B 或原 P0 因果证明。
- 最窄修复仅把 B 的原全部故障/完成/owner/内存/seed 断言块原样移到本周期所有 mock poke 后、fire 快照/clock 前；所有断言、窗口形状、early-done、队列和硬件保持。Spec 与 direct driver 机械逆变换恢复旧全字节；补首 vector request/result 实际 fire 的 tick/protocol_only 有限事件，不输出 payload。
- 下一次沿独立 `public21_downowner_protocol_driveorderfix_20261102_once` 唯一接续。workflow/guard/runner 精确三处 nonce 同步，并保真实临时 Git→guard.main→actual runner 全 11 阶段回归。云端原 whole7200/runner6600/各阶段内存CPU盘预算与 no-artifact 范围不变；原三次云失败与本地证据均保留。没有借机修改 RTL、缩小 banks、放宽数值或 success 门。
- 主任务仍原五块完整数值，whole0/5 INCOMPLETE。后续 B 的协议通过也只说明此 mock 合同下跨边界；原 P0 故障是否同因仍须实际工程证据，不以 fixture 修复冒充硬件修复。

以下此前完整计划原样保留。

---

## 2026-11-02 09:46 UTC：修正恢复入口的精确 nonce 三处闭包

- 原 targetdirfix run `41422562975` 在 09:41:04 UTC 的 IDENTITY 前置门失败；有限回执明确 runner 行 36 / last_completed_stage=null。workflow 与 guard 已换新 nonce，但 runner 仍硬锁最初 once 路径，交接遗漏导致确定拒绝。此轮没有任何 prep、compile、emit、backend 或协议阶段执行，不是相对 TargetDir 修复失败。
- 本次仅同步 workflow path、guard 的 LAUNCH/NONCE、runner 的 exact launch_manifest_path 为独立 `public21_downowner_protocol_identityfix_20261102_once`。不改 exact path / source parent / attempt=1 / source Git identity 门；不泛化可接受路径，不重新激活旧 nonce。
- 增加实际入口回归：临时真实 Git source commit → 单新 launch commit → 读取真实 workflow 的路径/入口 → 执行原 guard.main 并保存真实 identity/blob → checkout source → 原 runner.main 全 11 阶段编排。Git 与 guard/runner 身份门不 mock；下载/EDA/权威工具仍明确 synthetic mock，不冒云端资格。旧路径反例须在首阶段前拒绝且不创建 work。修复了此前手工构造旧 identity 使测试没覆盖实际交接的缺口。
- 原 run 41422562975 闭日志与 41419416366 / tiny 负正证据全部保留。相对 TargetDir 修复、真实 B、硬件、源角色、预算和 no-artifact 边界一字节不变。下一次唯一新 nonce 接续仍仅协议诊断，不声称原 P0 resetRequired 或五块完整数值已解决；whole 数值仍 0/5。

以下此前完整计划原样保留。

---

## 2026-11-02 09:35 UTC：B 源码诊断的相对 TargetDir 修复（非硬件通过）

- 原唯一云端 run `41419416366` 已 failure：JDK、编译工具、JAR、Verilator 工具、fresh-host 五准备阶段及 165 源 compile 均 strict0；compile 120.6446 s / sampled RSS 1,653,260,288 B。emit 在 6.2896 s / sampled RSS 246,501,376 B 以 native1 关闭，errors=[]、cleanup/EOF/gzip 完整；仅观察到 BEFORE_ELAB 与 ILLEGAL_ARGUMENT / REQUIREMENT_FAILURE 有限类别。未到 backend、native load 或 B 协议执行，未上传 artifact；原远端具体子异常 stack 未传出，不追认已看到。
- 独立 32-bit 寄存器 + Boring 小例沿相同官方 Compiler API 真实复现：绝对 `TargetDirAnnotation` 被 `Compiler.requireTargetDir` → `os.RelPath` 拒绝。旧 Scalatest 入口使用相对目录；这是一处已证明的 host API 前置缺陷，不归因硬件 fault。
- 最窄修复仅令 annotation 使用 `out.relativeTo(os.pwd)`，新增精确还原为原绝对 out 的等式；不 chdir、不更换输出实体、不放松空目录、LOW/SV 存在或其他成功门。同限小正例完整走过 elaborate → LOW → TopmoduleInfo → harness → SV，3.4007 s / sampled RSS 154,628,096 B，strict0；新 EmitOnly 也真实类型编译成功。小例无 DownOwner/banks/backend/native，不冒 B 资格。
- 补固定阶段 checkpoint 与有限异常类别 / 已 pin Scala basename + 正行号（最多 8 帧）；原异常继续抛出，闭日志完整 hash 验证与 8 KiB 投影门保持。无 raw error、路径、payload 或额外 artifact。
- 接续仍同真实 B / 原 159 硬件及 6 fixture 源、原 mock Matrix/vector/DDR 范围；单独新 nonce `public21_downowner_protocol_targetdirfix_20261102_once` 在源码 CI 成功后唯一启用。不是重试旧 run；原失败与小例负/正对照保留。
- 云端 whole 7200 s、runner 6600 s 与所有阶段预算、6 GiB 最大阶段 RSS、AS 15 GiB、512 MiB 单文件、阶段 run 目录 2,000,000,000 B、共享 W/emitted 的 aggregate watch 12,081,306,272 B、1.5 GB 盘 reserve 均不变。2 GB 不冒称共享 emitted 的独立硬门。仅源码与有限日志，无本地 SV/classes/.so/数据上传。
- 任务主目标仍五块完整数值。现 whole 0/5 INCOMPLETE；五局部 input norm 精确相等不升级整体。B 的本轮修复、小 API 对照或后续协议正例均不证明原 P0 resetRequired 已消除。

以下原计划全文保留，不覆盖历史失败或资格边界。

---

# 2026-11-02：P0 首 Dense 故障的同源 B 云端协议诊断（源码准备，尚未启动）

本次仍以完整五块数值验收为主目标。既有五块长窗及局部 norm 结果见下方完整保留正文：五个 input norm 局部逐 bit 相等不升级为全块通过，完整数值仍为 0/5。P0 已退休 norm 后在首 Dense 阶段报告 resetRequired；具体首次故障分量尚未定位。不得把 P1–4 的周期上限退出或小模型资格混作该故障的复现。

## 已闭的局部证据及明确未通过项

- A：真实 Public21 Router／Dense Coordinator／SumBridge，外部端口使用协议 responder；首个完整 N 窗加第二 N 窗第一 partial 终态的正常路径与错误 ng 反例通过。A 没有真实 DownOwner／banks／Matrix 后端，不能据此排除实际首因。
- B：保持真实 Router／Coordinator／Bridge／TransposedDenseDownOwner 和原容量、端口、时序的 banks，Matrix／向量运算结果／DDR 数据明确为 mock 零值协议流量；不是缩小后冒充 4096 MAC 硬件，也不授任何数值资格。目标是 ng0 的两段 K 归约、真实 tile／drain，再进入 ng160 首段 K 的终态。done 的发送依据模拟 Matrix 自身实际握手债清，不额外等待 DownOwner 写完，避免掩盖最后 tile 写入重叠。
- 本地 B 的三个资源失败均保留：512 MiB JVM heap 在 FIRRTL ResolveKinds 路径耗尽；1408 MiB heap 加 backend 子进程聚合 RSS 达 2,155,655,168 B 超过 2 GiB；释放 JVM 后单独 Verilator 仍达聚合 2,153,136,128 B 超过 2 GiB。三者均未到 B_SIM_READY，不是协议 PASS／硬件故障复现。实际已生成约 101.9 MB LOW、86.9 MB SV 和 633 KB JNA harness，但不据文件存在迁移成功资格。
- 两次直接 JNA 适配的 Scala API／作用域编译失败已留存；修后同包工厂与三小源实际严格编译成功（13.7956 s），新 emit-only 入口单源实际严格编译成功（6.9273 s）。这些只证明类型编译，不证明原生库加载、协议运行或全块数值。

## 唯一云端诊断设计与预算边界

本轮新建独立 source-only 协议诊断 workflow／唯一 nonce，先发布审定源码并检查 source CI，再另建仅含该 nonce 的激活提交。不得复用任何已消费的硬件构建 nonce，不重复原五个长窗。基于同一 159 源选择与官方 107 JAR 记录（106 classpath 条目及 1 plugin 角色），在新 runner 从源码重建；不上传本地 classes、LOW、SV 或共享库来替代源码闭包。仍沿原官方 Chiseltest LOW→SV 路径，不在此次引入尚未验证的新 CIRCT/CSE 变换。

整 job 单调时钟上限 **7,200 秒（2 小时）**，从首次 checkout 前开始，不是完成时间预测。runner step 上限 6,600 秒，预备阶段共享 1,800 秒且含其 cleanup；六个主体阶段依次为 Scala compile 300、emit 600、端口映射 120、Verilator 900、make 1,800、协议驱动 600 秒，主体合计 4,320 秒，另为六次 cleanup 各留 30 秒和有限摘要留 60 秒。每阶段实际开始前再次检查整 job 剩余时间与后续收尾预约，不重置计时。

最高阶段 RSS 6 GiB、另留 non-DUT 1 GiB 并真实核 runner MemAvailable；AS 15 GiB、单文件 512 MiB；2,000,000,000 B 的 tree 门仅约束各阶段 run 目录。共享 W/emitted 等输出目录不在该阶段独立 2 GB 门内，而由包含工作区和源码树的 12,081,306,272 B aggregate watch、512 MiB 单文件门及 1,500,000,000 B 磁盘空闲下限实际监督；不能把该共享域描述为已有独立 2 GB 硬门。单线程编译。此为新独立云端 job 的受审工程上限，不能拿本地 namespace 检查消除同主机未知旧 owner 的 5 GiB 预约，也不保证 B 必然能在这些上限内完成。

原 Scala 协议 driver 的完整 body 仅两处类型机械适配且反向逐字节相等；直接 JNA 端口名、方向、宽度、4710 个非时钟 ID 和独立 clock 与实际 LOW／SV／harness 四组 switch 对照，保留原 reset 一拍序列和所有断言。云端重新生成映射后必须匹配独立固定 typed 摘要，不由 actual 自赋 expected。协议输入仅为从已闭 manifest 精确投影的九个 shape／地址字段；不携 tensor／权重／参考输出，不冒原完整 manifest 或实际计算重放。

## 传递范围与失败处理

**没有新增 artifact 上传。** 不改变原七件传递范围；本诊断不下载或上传权重、参考 tensor、NPZ、原始日志、IR、SV、classes、共享库。子阶段 raw log 只在 runner 本地严格 gzip 保存，对外仅固定白名单的有限阶段退出／资源／cleanup／checkpoint／首故障分量及 SHA 摘要。失败沿本次身份诊断，不凭未知原因复制昂贵 CI；任何新的源变更、预算调整或复现结论均须另以实际证据核定。真实 Matrix endpoint、完整原始算术与全块验收并不因 B 协议诊断而完成。

---

# 2026-11-02 07:51 UTC：同一709e候选五块长窗已闭，完整block仍0/5

本节是1935实际云端阶段覆盖诊断的终态证据，不是新硬件或最终RTL验收。五块均启动并闭合；保留同builder128402、artifact05046aa9、SV3d148277、ELF709e88d0、固定4096 Matrix MAC/共享32-lane、原M128刺激与精度。整体原任务exit2，各DUT外监督native2/errors[]/cleanup及日志EOF完整。原数值门、MoE官方Torch topk与待用户明确的小ID同分契约均不改变。

## done（仅精确范围）

- 五块已闭输入norm局部输出均与官方reference逐bit相等：P0为官方BF16精确位扩展FP32存储，P1–4为原BF16直接字节比较。P0/P1/P2/P3/P4分别196608/131072/131072/262144/262144元素，均0差。不是每个内部算术节点通过，更不是whole block PASS。
- stage目标每块至少2个clean completion，实际全部只有1个，目标0/5达成；完整block 0/5，全部INCOMPLETE。P0在pc1 resetRequired，其余四块在pc1达到1,500,000 active-cycle限额；后四块reset_required=0，不误报同故障。

|profile|DUT阶段elapsed秒|采样最大group RSS字节|实际/目标completion|停止原因|完整状态|
|---|---:|---:|---:|---|---|
|P0|4535.7670|243900416|1 / 2|pc1 resetRequired|INCOMPLETE|
|P1|9540.2024|182784000|1 / 2|pc1 active-cycle cap 1,500,000|INCOMPLETE|
|P2|9546.2928|177741824|1 / 2|pc1 active-cycle cap 1,500,000|INCOMPLETE|
|P3|9474.7788|1827393536|1 / 2|pc1 active-cycle cap 1,500,000|INCOMPLETE|
|P4|9956.4737|1810763776|1 / 2|pc1 active-cycle cap 1,500,000|INCOMPLETE|

五份DUT阶段elapsed合计43053.514778秒（约11.96小时），不是含全部准备/其他清理的完整生命周期时长；采样最大group RSS最大值1827393536B，不是连续峰值保证。不能拿未完成block周期作利用率分母；有效MAC80%/争取90%仍未资格，未宣布RTL实测利用率。

## ongoing / todo

1. 以实际同源命令/矩阵接入/租约证据定位pc1：P0 resetRequired与P1–4周期上限分开归因。先由唯一调度进行已批准的有界A诊断，不能把检查写成代码修复或假定原因已证。
2. 保留五块输入norm精确匹配证据与各故障/限制收据；修复必须真实源码变更、独审、明确新身份并五块重测，不迁移旧局部/全链PASS。
3. 完整M128 Chisel数值链通过后冻结源码、输入、参考、配置，再同一份统一RTL同刺激回放。1024/1224第二档未定不阻塞128；不缩4096、不用DPI/软件替代、不把叶子/控制/结构或此局部norm冒完整通过。

有限证据：plans/evidence/five_stage_closed_20261102/SAFE_SUMMARY.json记录五closed RESULT、consumer/diagnostic/原progress log SHA、五局部norm摘要SHA、成本与确切范围；不含rawlog/binary/weights/reference tensor。本批仅更新已独审的有限证据与文档，不触发构建或数值执行。下面原中文计划完整逐字节保留。

---

# 2026-11-01 19:28 UTC：只读参考共享与更紧 TREE（host-only）

当前实际候选仍为 builder 128402 / ELF 709e88…，不重建硬件。上轮五个 300 秒校准全部严格闭合为 INCOMPLETE，0/5 完整数值，完整周期分母未知。新阶段覆盖窗口 10800 秒×5、每块 1,500,000 active cycles、目标 clean completed commands=2，整体 65400 秒（18h10）仅工程上限，不是完成预测或 FULL 资格；尚未启动。

本次修复 INSTALL binding 将新模式及 stage/P0/reference 预算 pin 传到实际 runtime_reuse 原准入；参考分支仅 IMPORT_EXISTING_PINNED_RUNTIME + READ_EXISTING_PINNED_ARCHIVES。旧 CAL/FULL 与无参考复用 STAGE 的合法分支保持。

新增显式参考数据 hardlink：五块 122 tensor 共 44,262,400 B 在 fresh reference 目录共享已验旧 inode，RESULT 和所有输出/验证收据独立。EXDEV 拒绝，无 copy fallback；不 chmod/truncate/写共享 tensor。驱动只 O_RDONLY/PROT_READ/MAP_PRIVATE 读映射，DUT 写独立输出。hardlink 不是 OS 强制不可变保护；运行前后在原父监督/原 job clock 下逐 hash/inode 检查，超时或变化严格失败。

新 aggregate TREE=12,037,043,872 B，是比原 12,081,306,272 B 更严格的工程 cap，不能称旧预算已有已证参考分项或已知峰值安全。实际按 dev/inode 去重，避免重复 44,262,400 B 分配；8 GiB 磁盘 reserve、未知 owner 5 GiB、RSS/AS/CPU/墙时不变。全部 upfront/安装复用/监督/数值 phase 同 cap；最终真实 roots census 才决定准入。不得再清理或加入未消费 root 凑余量。

真实有界纯链已完成：839-source snapshot，all5 link 验证 2.646 秒、P0 完整同根数据/transport/corrector/load_binding 验证 3.943 秒，两原 RESULT native0/errors[]/严格 cleanup EOF。全5前后 hash+同 inode、fresh RESULT 已核；P0 原94,916,608 B输入不复制，reference同 fresh-root原 containment 通过。该纯链没有 live owner/DUT，历史 ABI 仅 schema，coverage false，不迁移数值资格。最终 catalog新增测试/证据不冒本次839执行身份。

待源码CI与新实际source、独立adapter/handoff、reference/P0数据 pin、fresh import/ABI与完整资源审批；1906未启动 proposal 保留，不偷换其已签身份。下面完整保留上一版计划正文。

---

# 2026-11-01 18:52 UTC：同一候选硬件的连续阶段覆盖诊断（非 FULL 预算预测）

本节为 host-only 工程接续；下方既有计划完整保留。实际候选 ELF `709e88d0…`、artifact `05046aa9…`、builder `128402f4…`、原 M128 输入、4096 Matrix MAC、唯一共享 32-lane bank、FP 运算及 driver 均不变，不重建硬件。

## 已闭实际校准事实

新候选五个 300 秒窗口已全部严格收尾，原验证器及摘要独立重算一致（`b85978dc…`）。P0–P4 活跃周期分别为 56,576 / 53,120 / 56,768 / 55,296 / 56,896；各仍 pc=0、completed commands=0、useful Matrix MAC=0。均为 STARTED_TIMEOUT_INCOMPLETE，数值通过 0/5，完整块周期分母未知。输入读写确有进展，但不能将写入字节数当已退休行数，亦不能用这些速度虚构后续 Matrix、QK 或 GDN 吞吐。

## 新模式及明确上限

新增 cloud candidate 专用 `STAGE_COVERAGE_DIAGNOSTIC`，独立版本化预算、校准来源、独立 review、实际 artifact/review、source catalog、审批 SHA 全部精确绑定。旧 CALIBRATION 与 FULL 模式的成功、预算和资源规则不被替代。

每块连续进程最多 10,800 秒、1,500,000 活跃周期；五块整体 job 最多 65,400 秒（18 小时 10 分钟，含原材料准备、监督与收尾预留）。这些是 watchdog 上限，不是完成时间承诺，也不是 FULL 估计。后验 target_completed_commands=2 依据真实五份程序：pc0 input_norm，pc1 为首个 matrix（P0/P2/P4 q，P1/P3 qkv）。只有 driver 按原 clean completion 加 AXI drain 后真实退休才计入；不在线提前停止，不以写入量替代。更后的 QK 或 GDN 仅观察，不保证到达。

## 纯 P0 数据复用与资源边界

为避免重复生成已严格闭合的 P0 input_only，新增受审纯数据复用路径：逐 pin、形状、原 BF16 转置/扩展、输入/reference/rope、固定程序与原转换源码契约复验；实际读取旧纯 provider 数据，新的程序 metadata、TSV、runtime、连接、ABI、owner 和 DUT 输出仍隔离生成。不得读取或迁移旧 DUT 输出/数值 PASS。旧 metadata 的精确副本仅作来源证据，保留原路径语义，不伪造历史收据。

TREE 与 8 GiB 获取余量不变，RSS 2 GiB、AS 2.5 GiB、consumer 512 MiB、未知旧 owner 5 GiB 与额外 1 GiB 预约不变。只将代码实际读取的目录纳入 census/watch，禁止添加无用旧 run 根来虚增 live bytes。最终新身份必须通过当场完整盘门与资源审查；源码或静态节省量不构成准入。

实际双根纯链已在当时 830 源闭包执行：完整转置/扩展及原 probes、fresh program/TSV、hydrate/corrector/assemble/load_binding/spans 均通过，严格 native 0、4.202 秒、采样 RSS 116,805,632 B，94,916,608 B 输入未复制或 alias，未用共同祖先或手改程序路径；历史 ABI 仅作 schema 字节副本。三项真实小 metadata 负例均拒。该证据不授 live owner/新 ABI/DUT 资格；最终测试夹具/有限证据闭包变化另列。后续仅 host-only 发布/CI，不能把诊断结果自动提升成完整五块数值或最终 RTL 验收。

---

## 2026-11-01 17:58 UTC：精确 host adapter 已审路径清单闭包修复

- `ad81c756` 云端接续入口 0.17 秒拒绝，尚未创建 binding/job、未 runtime/ABI/DUT。实际 adapter 全差异扫描发现五个此前已审 host-only 路径未列许可：contract-domain 三个小证据/复现工具，以及 candidate_observation_contract.py 与其旧测试；不是新硬件差异。
- 仅将这五个精确相对路径加入受独立 review 约束的白名单，不使用目录前缀、不删完整 builder/executor catalog diff、实际字节和 review 绑定门。原首次失败保留。后续必须实际完整 adapter / handoff 前置验证所有差异后才生成新执行身份；不再逐首错误重跑。
- 仍同 artifact `05046…` / ELF `709e…`，driver/SV/参考/输入/资源预算/五个300秒窗口不变；无新增 GitHub build 或 nonce。完整数值与最终 RTL 仍 0/5。

## 2026-11-01 17:48 UTC：候选 builder／executor 合同路径域接续修复（仅 host source）

- 新候选实际 artifact `05046aa9…` / ELF `709e88d0…` 不重建、不改硬件。前一 `2e0b34cf` 云端身份 `3ffacfdc-4614-4919-bb29-40f6482ecfe4` 已通过原现场盘门、archives、三个 fresh runtime、实际 startup ABI、P0 initialize / rope / provider / transport；`p0_connect` native 1 且 strict cleanup / EOF 完整，DUT 未启动。
- 原闭日志确证：外部独审 review 的 source contract 固定在 builder 的真实路径，而 checker 错要求它就是 executor 本地路径；二者实际合同字节相同。最小修复保留外部 review / context 原 pin 等式及 immutable artifact，不改外部来源；单独核 executor 的固定 HERE 合同角色、无 symlink、唯一当前 catalog 行、实际大小与硬锁 SHA 全相同。
- 实际只读 P0 纯链已通过：新 checker 的九源映射、hydrate 原构建证据、corrector、assemble、consumer.load_binding 及完整 candidate compile proof / source_links，最终 y 786432 / K 131072 / V 131072 spans 与 anti-oracle 原门。fixture 为保旧材料只读使用共同祖先 root 与原 program 路径；这不是生产 material containment、live owner、资源或 DUT 执行资格，原两次 fixture 路径拒绝保留。
- 只发布 host-only checker / 精确测试与必要闭包，不改预算、driver、SV、参考、输入或任何 nonce；后续新 executor 诚实采用独立 adapter 身份沿同一七件。局部 pure source projection 不代 live owner 或 numerical admission；完整 M128 数值与最终 RTL 仍 0/5，FULL 工程预算须实际候选进度支持。

## 2026-11-02 01:31 UTC+08：实际候选已接包，云端磁盘准入拒绝；只补有限回执

GitHub 原 run 41323045817 成功，七件 artifact13093285720 已唯一下载并逐字节校验；新 manifest05046aa9…、ELF709e88d0…、SV3d148277…，原159源码/122ABI/4096MAC/唯一共享32bank 已作独立结构与来源审查，不是完整数值 PASS。新候选本地 UUID2e52b6f5…已在原 upfront disk 门失败退出1，job目录尚未建立，runtime/ABI/DUT未启动。后验 free9,453,305,856B、watched8,108,815,617B，原 TREE−L+8GiB 需12,562,425,247B，缺3,109,119,391B；后验数值不冒原瞬时快照。

本小批仅给原upfront gate增加绑定原binding SHA的有限数值回执，原失败/成功判据、TREE、free8GiB及所有预算完全不变，不输出目录/rawerror，不新构建ELF或激活CI构建。下一executor如实独立source身份，保128402 builder与七件原bytes，完整旧输入来源/实际ABI/原参考数值门仍执行。可恢复临时文件单批归档清理另有独审，不删唯一证据/输入/引用中的Git对象。完整M128及最终RTL仍0/5。

## 2026-11-01 15:39 UTC：修复候选打包与导出目录接线

原 packfix run 41314704781 已失败终态：20 构建阶段有限原收据均 native0/cleanup/EOF，构建步骤成功后 export 错读旧 frozen_artifact 目录；实际 candidate pack 输出 model_candidate_artifact。Artifacts API 为空，无可下载 ELF，不继承上次产物 PASS。当前只修固定路径并额外核 manifest.path 精确绑定，原七件非空、全部严格验证、9000/7200 秒和 O1 flags 不变。真实 subprocess CLI 已串联 record→pack→verify→export→workflow 七件目录夹具，normal/-O 新版 CLI0、旧版明确目录摘要拒绝，28严格合成阶段与9导出/5打包负例均过；先核805真实源pin，再用独立合成catalog实际执行所有验证。追加3证据后最终闭包另核，测试数据明确 synthetic，不冒实际候选结构或完整数值资格。完整 M128 与最终 RTL 均 0/5。

## 2026-11-01：编译完成后源码pin空文件兼容修复

- 原candidate run41306209752实际20阶段全部native0且严格收尾，真实122端口门通过，host_archive约2933秒、host_link约15.56秒；失败发生在后续pack source pin检查。七件未导出，完整数值仍0/5，不把编译成功冒验收通过。
- 原封包器误将产物必须非空的regular门用于所有源/工具输入。固定IDMA manifest中实际合法0B `.gitkeep`可精确复现旧拒/新过；远端首个失败path未记录，保持这一观测边界。
- 仅source/tool pin允许0B并继续全路径/上界/完整可信SHA校验；所有七件产物和JSON/输出原非空门不改。新增真实record→pack/输出验证合成回归及反例，合成证据不替代新实际构建。
- 补完post-build有限分类，原失败/清理/预算门保持；不上传rawlog/权重/参考。159硬件、4096共享资源、原驱动/CPP严格flags、7200/9000预算和七件类别都不变。下一构建仅在源码独审与测试后由唯一writer恢复。

---

## 2026-11-01：恢复原观察链与严格122端口联检

- 实际 Dense 新兼容变换已通过；后续 emit_host 明确观察到85而非原122端口并拒绝，原合同/驱动不放宽。源码审查确证新norm复基丢失原Top/Owner只读观察转接，现仅插回原baseline已有输出/default/profile/真实producer接线。
- 完整159选择对旧基线逐字审：148未改源保持；原八观察override其中六个原样，另五norm替换逐删除审未见无关回退。新增保真测试固定完整Top IO与实际转接、148/6源、37观察字段和原driver，不只数端口。
- 已真实复编11norm源并补编当前实际rawScore bundle来源；局部机械提取实际Top IO的Chisel官方LOW生成完整有序typed122，与原driver精确相等。历史classes缺3字段和方向枚举表示问题均明确归因并保留失败；小fixture不是完整Top或五块数值通过。
- 同时修复候选emitter方向枚举表示：只Input/Output映射原canonical input/output，原122名称/类型/顺序门不变。后续完整候选仍需新实际产物结构复核、原五块M128全数值验收，当前0/5；原4096共享资源/7200及9000预算/编译flags/七件范围不扩。

---

## 2026-11-01：Dense 仿真存储转换的严格结构匹配

- 反馈修复后，实际原Top HIGH/官方LOW及candidate canonical已经通过（1058 modules / 9127 annotations）；后续变换明确报 `DENSE_ACC_LOCAL_SHAPE`，不是OOM/超时或数值失败。原stage严格收尾保留；缺少新HIGH正文，具体原require仍不冒确定。
- Dense算术/清除/索引源码与旧版逐字节相同。候选兼容转换由硬写2个自动临时名，改为证明完整typed全零构造和所有驱动/消费/条件位置；旧生产转换不改。131072bit容量、16并行写端口、原异步读及最后连接优先级保持，不减少4096 Matrix资源。
- 实际小Scala/官方Parser对保留的历史Core验证新旧完整AST、序列化、canonical相等；alpha改名正例、旧类拒绝及10坏例均通过。源/安全摘要在 `evidence/dense_zero_closure_20261101`。初次API与测试期望的Block扁平化错误均如实保留，未删等价断言。
- 本次未改变159硬件源、数值公式/刺激/驱动/编译flags；新helper与finite predicate作为独立构建源码身份。新实际HIGH必须重新通过完整结构门，不能把局部历史AST结果当新硬件、完整模型或最终RTL通过。
- 原构建7200/9000预算与七件授权范围不扩；无权重/参考/rawlog/原IR上传，当前五块完整数值仍0/5。

---

## 2026-11-01：共享 Vector32 P0 租约当前故障反馈修复

- 原候选构建已通过 JAR 全校验、159 源编译和 helper 编译；`original_high`（实际含官方 LOW 检查）native1、资源监控无错误且严格收尾。远端子异常当时未导出，不臆称已经拿到其原因。
- 静态发现当前 authority 故障反射回同一请求 valid 的组合环。真实 adapter/lease 小模型用原官方 LOW 检查复现旧 `CheckCombLoops` 拒绝；只去反射并保留 owner 期间寄存 poison 后，同一检查 strict0。其他独立故障和 held 请求债规则不变。
- 修后原9协议case在真实32-lane bank/原 scalar 的 Chisel→Verilator 局部模型全部通过；不据此宣称完整 Top 或五块 M128 数值通过。有限证据与3份可复现小模型源码在 `evidence/rms32_authority_feedback_20261101`。
- 唯一硬件源变化是 `HostOrderedRms32WiringV1.scala` 的故障反馈；159 源选择/生成合同显式形成新身份。4096 Matrix、唯一32-lane bank、所有数值顺序与驱动保持，旧生产准入门不动，不以观测值自动填接受值。
- 构建器新增原子阶段 native 失败的有限闭日志投影，保留固定阶段、有限异常类别与符号，不上传 rawlog。原7200/9000预算、O1严格 flags及七件传递范围不扩。下一次完整候选构建仍须真实结构复核和五块原验收，当前数值0/5。

---

## 2026-11-01：候选模型 FULL 看门狗预算入口（仅执行端源码）

- 此次不改正在构建的 `c50e7dd8`、159 源硬件、共享资源、SV 生成参数、驱动或编译 flags；保留已消费的 jarfix launch。构建与执行源码身份分别记录，不伪称同一全源码版本。
- 新 `MODEL_CANDIDATE_FIVE_M128_FULL_EXECUTION_BUDGET_V1` 只用于实际候选 artifact：绑定真实 artifact SHA、独立候选审查 SHA、同候选校准摘要及独立工程预算审查；旧生产 V1 仍保留原硬件基线门。缺预算或证据仍拒绝，不从旧 O1 短窗迁移完成时间。
- FULL 只控制明确的五块时间和周期上限；4096 MAC、M128、原数据与全部数值验收不变，原每块 18000 秒／1e9 周期上限不扩。候选通过也不自动成为 production 或最终冻结 RTL 验收。
- 本包没有填写实际 FULL 预算、没有启动新任务、没有新数值结果。真实候选构建产物、结构审查及运行进度尚待取得；用户主线授权已存在，剩余是工程证据和预算准入，不是等待重复用户许可。
- 轻测：21 项相关测试及执行端 315 项测试，normal / `-O` 各通过。新增适配白名单仅精确允许执行预算源码与其测试，不放宽硬件变更范围。

---

## 2026-11-01 10:40 UTC：候选构建准备入口错接修复（TEMP，完整数值 0/5）

候选源码 fd366 的唯一构建 run41297957281 于 bootstrap/jars 严格门失败，尚未进入 159 源编译、IR/SV 或数值。Actions 原日志只有 `bootstrap failed jars`，原子收据未上传，不能倒推网络/内存原因。冻结同源码、同 `--download-jars` CLI 已本地真实复现：旧 restore_inputs 在任何下载前先检查旧155源码，精确拒绝已替换的 GdnRuntimeRmsNormOwnerV3.scala；因此确认候选 bootstrap 错接旧生产恢复入口，旧锁本身正确。

本次只新增候选专用 restore_model_inputs：先验原已审 159 generation contract/overlay，再使用原 107 条 JAR 记录（106 classpath + 1 plugin，plugin 文件兼列 classpath，共 106 个 distinct 文件）的同 URL、顺序、长度与 SHA，仍写原 cache 路径供既有 materializer/classpath 使用。不改旧 restore_inputs/155/canonical 生产锁，不改 11 个硬件源、driver、Matrix/Vector 物理资源、FP 顺序/BF16 或参考合同。

同时补 bootstrap 八阶段原 supervisor 返回的有界诊断和 JAR 子进程固定枚举状态；不输出原始日志、argv、URL、路径或任意错误文本，不把诊断文件代 strict RESULT 或授权。原每阶段 wall/RSS/AS/cleanup、1800 s prep、7200 s 含 prep、9000 s whole 及七件类别/总大小限制均不变。原失败身份保留；新一次性 nonce 仅供经源码独审和 CI 后的同范围修复验证，不重试已消费 attempt。

实际无网前置审查另核：新159源字节、原13 Matrix provider源码物化（43,047 B）、原 iDMA 全清单和308 provider lexical ABI、115 Verilator 操作文件哈希。它们不替代 fresh CI JDK/GNU/工具下载和完整 binding，更不代表新整体结构/数值通过。新 artifact 仍永久 UNREVIEWED，实际结构独审前不准入云端模型数值。

**当前完整 M128 模型数值 0/5，最终冻结 RTL 0/5；本次是准备源码修复，不是数值或性能 PASS。**

---

## 2026-11-01：保序 32-lane RMS 候选进入统一模型构建；完整数值仍为 0/5

### 已完成且有实际证据
- 原 O1 同一 4096-MAC 硬件的五个 M128 诊断窗全部真实启动并严格收尾，均为 `STARTED_TIMEOUT_INCOMPLETE`，不是数值失败或通过。active cycles 为 61,824 / 60,736 / 57,856 / 64,448 / 57,728，外层观测速率约 189.7–211.7 cycles/s；出现实际写回，但均未完成首命令。完整块总周期未知，不把短窗外推作完成承诺。
- 原 P0 两次串行 norm 的静态周期下界为 4,464,640；按完整语义矩阵 MAC 分子，固定 4096 分母的静态利用率上界约 32.891%。这是当前基线的源码下界/上界分析，不是测得利用率；普通 C++ 优化不会改变硬件周期瓶颈。
- 新候选复用唯一共享 32-lane bank，保留每条 FP32 归约链的逐项顺序和舍入，不新增第二算术 bank、不减少 4096 Matrix、不缩五 profile 或 M128。P0 保留 Div1536 和两处 BF16 物化；runtime 保留 reciprocal multiply、gamma=1+w 和最后 BF16 物化。P0 sum 新增 137×FP32=4384 bit 工作寄存器与 512 bit SRAM bridge 缓存及控制；仅 sum 借用 32-lane bank，normalize/gamma 原 16-lane 路径保留。新增寄存器/控制/握手不是免费资源。
- 实际局部 Chisel→IR/SV→Verilator 回放已完成：P0 六行精确 sum（含真实 SRAM bridge）、runtime H1024/H2048 各 T1 的逐中间量与最终 BF16，以及实际共享 adapter/lease 的 9 类协议/背压/故障测试。11 个生产源类型检查通过。它们不代表五个完整 M128 模型通过，也不证明全链 II=1。

### 本次源码的实际边界
- 原固定 155 源清单/哈希准入门及旧 canonical/观察者生产准入门保留，并明确拒绝新硬件。独立 `MODEL_CANDIDATE` 入口以原顺序 155 源的 7 个精确替换和 4 个新增形成 159 源闭包；新构建仍使用原 20-stage 预算路径（首阶段版本化命名），7200 s 包含准备阶段，外层 9000 s，不扩大编译资源或 O1 flags。
- 构建只收集实际 typed IR、ordered annotations、122 个 typed host ports、SV 及结构不变量；所有新产物永远标 `UNREVIEWED_MODEL_BUILD`。实际 Matrix 4096 / 唯一共享 bank / 五 profile 一致性必须经外部独审后才允许云端候选数值评估，不能把 observed hash 自动当 accepted hash。
- 新七件仍仅 ELF、同源 SV、driver 与四份元数据；不上传权重、NPZ、参考数据、原始日志。source_manifest 总文件保持 16 MiB 上限，原其他单件/总包限制不扩。新候选必须使用真实新身份和完整编译证据，不继承旧 ELF 的数值、ABI 或性能资格。
- 云端完整接线新增独立候选 review pin，从可信预算/调用贯通 prepare→flow→tail→handoff→consumer→summary；纯合成全链已实调完整 checker 并通过反例，不是实际新硬件准入。DATA_REFERENCE_ONLY 可复用严格重验的原 70 权重与五份官方参考，仍核全部 51 参考源、刺激和字节；它不迁移旧 DUT/ABI/runtime/数值 PASS，也不谎称新旧 SV 相同。
- 原实际基线、失败收据和新测试初始失败全部保留。测试中的旧 155 预期改为精确拒新候选，新 159 门独立正验；不存在为了通过测试改写旧生产接受哈希。

### 下一步与未闭环
唯一 writer 在联合源码独审和源码 CI 后启动一次候选构建；真实七件到达后做结构/同源/工具/loader/资源账单独审，随后沿完整五 profile、M128、原参考与严格数值链执行。完整块工程预算必须依据新模型实际进度和资源形成，不能无条件套用 300 s，也不能把超时当完成。用户已授权该工程主线，不需要再次询问同范围许可。

**当前：完整模型数值 0/5；最终冻结 RTL 验收 0/5；新整体候选尚无实际构建/结构/全块数值资格。**

---

## 2026-11-01 07:36 UTC：明确 prelaunch 内存拒绝；狭义退出修复（INCOMPLETE）

795d实际新O1恢复的P0 provider返回已保存，精确 `ValueError: locked memory gate` / worker_started=false / native_exit=null / 无worker目录。此前archives、3runtime imports、startupABI、initialize、rope共7阶段原收据全部native0/cleanupEOF。未运行DUT，不是数值失败。旧require_cleanup将没有启动worker的拒绝也无限hold；本次仅精确session5387中断，工具实际exit130，原证据保留，未知旧owner5GiB预留不变。

源码仅新增狭义可证明prelaunch分支：固定c298监督器源码SHA及其gate→mkdir→Popen→workerflag顺序、完整返回字段/精确3种前置错误/无owner与log/零采样/reader未启、实际输出目录不存在（含symlink拒）共同满足才写独立PRELAUNCH_REJECTED marker并raise INCOMPLETE。不能只凭workerFalse——Popen后的leader验证失败也可能尚未置True。已启动或未知cleanup缺失仍保持原hold，不伪cleanup PASS或数值通过。

外部下一诊断预算拟经独审只将三处group RSS收紧到2GiB：dut_rss_bytes、install.rss_bytes、reference.rss_bytes。DUT及角色AS仍2.5GiB、consumer512MiB、旧owner5GiB+1GiB余量、五300/12900与所有运算/线程不变，内存准入门因此为8GiB。numeric_reserved_increment为磁盘增量，不改。此为更紧采样RSS条件诊断，非硬group隔离或完整执行足够保证；实际超限仍INCOMPLETE。源门本就支持，不修改cloud_budget源码，不通过缩硬件绕资源。

同已实际构建的新O1 ELF df229/SV9a8c/driver343e保留，不重build；新source经过独审/CI后产生新可信executor与预算身份、fresh runtime/ABI/实际views验证。当前完整数值仍0/5，FULL预算缺工程完成证据而非用户授权。

## 2026-11-01 07:24 UTC：O1 构建成功；云端预启动失败与返回证据修复（INCOMPLETE）

原诊断 build run41277679022 成功：新共同 O1 ELF df229150…（77,405,168 B），SV9a8c/driver343e实字节与原冻结相同，五编译实际收据已审。20阶段有限诊断均native0；这不倒推第一次 host_archive UNKNOWN 原因，也不构成五块数值通过。

本云新7824206 executor/新O1实例在 fresh runtime import 的第三08B阶段早期拒绝。archives、35B、Qwen2原收据均native0/cleanupEOF完整；08B无worker目录，原返回未保存，因此具体类别UNKNOWN，不据当前内存倒推OOM。未到startupABI或DUT。70原权重/五软件参考已全hash重验，未重下载/重forward；原输入、旧两次失败及七件保留。

本次最小host-only修复：复用runtime、fresh安装及bind、cloud/CI controller stage、numeric tail在supervisor返回后、原检查前，各向已存在本地results/bindings/phases写独立`*_SUPERVISOR_RETURN.json`原调用返回。所有runtime/ABI/initialize/provider/connect/DUT主链阶段由此覆盖；不把它当worker RESULT、不放宽成功门、不修改callback/order/finally/caps。仅本地诊断，无新增上传或原日志外传。bootstrap/build不在本云执行链；原构建20stage已有有限stdout诊断，未为了本修复重新编译。

原2.5GiB/consumer512MiB/旧owner5GiB+1GiB余量、五300秒/12900保持。已结束身份不续作owner，新executor源码经审查/CI后生成新可信身份并fresh runtime/ABI/实际views重验，复用同新O1 ELF而不重复build。当前完整数值0/5，FULL工程预算仍需实际速度/资源，并非缺用户授权。

## 2026-11-01 05:33 UTC：O1 构建失败与一次同约束诊断（INCOMPLETE）

- 原 O1 run `41272957145` / source `4255e062f90e62b7c54ebde3fa09bb39021dfa45` 在 `host_archive` 返回后被严格门拒绝。前3子 archive 仅有控制流进入后续阶段的证据，不冒完整可下载收据 PASS。7件导出/上传跳过，无新 ELF。原因类别 **UNKNOWN**：失败时原 RESULT 留在已不可恢复的 runner；整个 build step 3767.803 秒不能当 host_archive 耗时，也不判 OOM、wall 或编译器错误。
- 最小新增：每个原构建阶段返回后、严格检查前，将固定≤8KiB有限诊断输出到原 Actions stdout，含 native/有限错误类别/原 caps/实际耗时CPU/RSS/tree/file/cleanup/EOF及原 RESULT SHA；无 argv、路径、任意错误正文、编译器日志或数据。原严格门不变，诊断本身永远不是数值通过。
- 下一唯一诊断构建只为恢复具体失败类别：仍 `CPP_O1_STRICT_V1`，原 build7200/whole9000、host_archive3600秒/RSS8GiB/AS15GiB不增加；同4096/SV/driver/五块M128数据和FP契约不改。不声称实际编译问题已经修复。新nonce不复用已消费strict launch；不得无新信息反复重跑。
- 当前五块完整数值仍0/5，旧O0五块仅实际300秒有界INCOMPLETE。P0已独审静态两norm≥4,464,640周期，完整语义矩阵MAC6,014,828,544给固定4096完整block利用率上界32.890983%；仅当前P0架构上界，非实测、非其余四块。O1不会改善该硬件周期瓶颈，80/90%仍需后续架构整改并重验。先恢复可执行共同ELF和真实数值主线，不偷改当前冻结硬件。

## 2026-11-01 04:25 UTC：O1构建已唯一启动；执行器纯输入跨编译复用修复（TEMP）

- 原构建源码4255e062、唯一launch2f23f49d，O1 build-only run41272957145运行中；本次执行器修复不修改其源、flags、硬件或作业，不启动第二构建。
- 发现原retained输入门误把整个ELF artifact SHA当参考数据身份：新O1 ELF不同会拒绝原70权重/五完整官方M128参考。现候选仅允许独立钉住的旧/新实际manifest在完整4096、五profile、32字段、原route/执行层级同一且SV与driver实际文件逐字节hash同一时重验并复用数据；仍核完整material-producing源码/配置与所有权重/参考tensor，不继承旧runtime owner或DUT结果。
- 新ELF的真实构建策略、编译收据、远端artifact、loader/DSO、资源与全部五块数值门照常独立验证。相同SV/driver不是新ELF数值PASS；实际新产物尚未到，跨新产物资格仍待真实bytes。
- 这是executor-only后续源码，builder4255冻结不变；保留已消费launch，不为输入门修复重复build。FULL工程预算仍待真实优化速率与资源，当前完整数值0/5。

## 2026-11-01 04:17 UTC：五块实际窗口已结束；共同 ELF 严格 O1 候选（TEMP）

- 实际 executor dcc3 / builder e015 / 同一 ELF a8884d6e…，五块均完整4096资源、128 token配置，逐项真实启动。原收据与独立聚合：五项 STARTED_TIMEOUT_INCOMPLETE；0/5完整数值通过，尚无冻结后最终RTL回放。
- 最后 active cycles：P0 16704 / P1 17344 / P2 16960 / P3 17472 / P4 17216；约54–56 active cycles/外层秒。全为首命令pc0，暂无完整输出；不据此称死锁或数值FAIL。完整block周期分母、MAC利用率与剩余时间仍未知。
- 原实际编译统一O0已经实际argv证实。本批准备明确 CPP_O1_STRICT_V1：所有child/global/host/driver统一 -O1，并显式 -fno-fast-math -ffp-contract=off；无native ISA/LTO/PGO，生成SV/driver/硬件/FP32与每步BF16参考契约不改。新ELF需真实新构建身份、完整五phase编译收据、ABI与五块全部重测；不能迁移旧性能或数值PASS。
- 原build7200秒（包含更紧prep1800）、workflow9000秒及每stage资源上限不扩大。新O1实际峰值与耗时未知，不能凭原O0采样保证完成。源码CI、mock/轻测不冒实际构建或模型通过。
- 监督候选保留全roots每轮census、fresh lstat、所有限额/cleanup，仅降低路径对象开销。已闭实际树一次只读对照旧4.404秒/新0.601秒，计量7,635,776,266字节一致；有先后缓存混杂，不当DUT倍速证明。
- 同源builder/executor使用显式原loader时，允许仅在完整catalog字节相同、空diff与独立review全部绑定后走同源分支，不为满足旧异源条件制造第二commit；绝不免除ABI、liveowner与资源门。
- FULL工程预算仍待优化后实际速率/资源形成，非缺用户授权。不得继续用无解释300秒循环替代完整M128主线。本批尚未启动新重构建，原e015七件与全部失败/结束收据保留。

## 2026-11-01 03:18 UTC：P0 builder / executor 源路径命名域修复候选（未数值通过）

- 实际 executor `1aa8dcbf` 恢复任务已结束：startup ABI、P0 initialize / rope / provider / transport 均有严格 native 0 收据；`p0_connect` 在读取 GitHub builder 的 `/home/runner/...` 原始源码路径时拒绝。未执行 DUT，五块 M128 硬件完整数值仍 **0/5**。
- 九个源码锚的当前本地文件逐项满足原 builder 冻结 manifest、原 generation pins、独立 locked contract 与 executor catalog 的 bytes / SHA；错误是将原构建路径当成当前文件系统地址，不是硬件或参考数值差异。
- 修复只允许独立批准 cloud binding / adapter / handoff 验证之后，在内部传递原始路径与本地路径的对应关系。原 builder manifest、编译 argv、GCC/header 证据、Scala / C++ / ELF / SV 字节不变；同 job 默认路径严格门保持，三个 runtime program 锚不参与迁移。
- 新隔离 `actual_r2` 原四阶段输入 fixture 已全部 strict/native0，25.921s；原材料与源码前后字节校验通过。首轮 fixture 前置无回执原因未知，现场保留，不解释成数值失败。随后真实无 DUT 消费检查 strict/native0（0.652s），原 corrector / fixed155 / GCC/header/link consumption / coverage / consumer.load_binding / 全部 P0 final spans 均通过；gate/up 仍 mandatory、未观测，不继承旧 owner 活资格，不算模型或 RTL 数值 PASS。
- 源码回归 497 项 normal / -O 全通过；696 源闭包逐项核验。上述实际离线检查使用闭包 `f416a26fd27813811af43e81bce558572283040b4d111139eb6613e4174557b2`；真实运行仍须新身份批准输入、fresh runtime 和 startup ABI 重验。
- 本次不增加预算、资源或硬件，不重新构建 / 下载权重；五块仍使用同一 e015 构建产物。FULL 工程预算仍待实际 DUT 进度与资源证据，不是缺用户授权。

## 2026-11-01 03:00 UTC：真实 ABI 通过；物化依赖历史 pin 修复（SOURCE-ONLY，数值 0/5）

- 新云端执行身份 `25a54e69-5286-4372-8270-048eeff37aa7` 的 startup_abi 已实际 native=0、8.609 秒、strict cleanup/EOF/gzip 完整；六库真实 resolved path/bytes/SHA 等于原 builder。仅启动 ABI 身份资格，未到 DUT 数值。
- 随后 p0_initialize 因物化 REPO_DEPENDENCIES 的旧参考源码 pin 退出 1。整表219项仅该项漂移：参考源码在更早 ad299 已加入同次官方 gate 只读观测，实际 e015 builder 与当前 executor 的源码字节完全相同，原 baseline 输出/cache 精确比较不变。本次不修改参考算法或 provider 代码，只同步该既有版本 pin 并补它已存在的 router_local_observer 依赖，上层 metadata 锁同步，历史旧表保留于 Git。
- 继续整链审查：P0/P12/P34 源依赖、原 PROGRAM_PINS、实际生成 P1–P4 的12个 program 文件、numeric connection 与 consumer 硬锁核实；不把固定源审计冒运行时 provider 数值通过。新增受监督五原始 initialize 接线测试，仅复制已验证参考并生成原程序，不执行模型参考 forward、loader、DUT 或硬件构建。
- 本轮五原始 initialize 已实际执行：P0–P4 全部 native=0、errors=[]、strict cleanup/EOF/gzip 真，总1.680秒；44,262,400字节参考 tensor 与45,449字节 RESULT 全部原字节复制，P1–P4原PROGRAM_PINS逐项相符，P0保持原空programs。未执行参考 forward、provider数学转换、loader、DUT或硬件构建；这是初始化接线资格，不是模型/RTL数值通过。
- 恢复仍使用新执行身份、原 e015 4096 MAC 的同一 ELF/SV/driver，70权重/五参考逐字节重验保留、不重复下载/重算。旧 unknown owner 5 GiB、DUT 2.5 GiB、consumer 512 MiB及原实际执行预算不变。完整模型数值/最终 RTL 均 **0/5**，FULL 工程预算待实际 DUT 进度证据形成。

## 2026-11-01 02:50 UTC：workspace loader 格式最小修复（SOURCE-ONLY / INCOMPLETE）

- 云恢复身份 `9a315419-ee75-47c8-9df8-d9a24762df69` 在 startup_abi 原监督下 native=1，严格 cleanup/EOF 完整；未到 DUT。保留原失败，不重构 e015 ELF/SV/driver，不重复下载 70 权重或五份已核软件参考。
- 实际原 loader 的 7 行 `--list` 输出含 PT_INTERP 绝对路径 `=>` workspace loader；旧 parser 不支持此格式而误拒。新增仅 workspace 显式调用的实际 PT_INTERP 精确别名；默认同主机 parser 规则不变，六库实际 resolved path/全 SHA 仍必须逐一符合原 builder。
- 独立格式诊断的 outer file cap 曾覆盖只读大 ELF 导致其监督门失败；827 B 输出可作为格式观察，不能冒严格 ABI PASS。新 parser 对保留实际文本及当前六库字节验证通过，仅文本/静态资格；下一实际完整 startup_abi 必须重新 native=0、strict cleanup/EOF 与实际解析全哈希通过。
- 本批仅源码轻测，不执行新 loader/DUT；硬件 4096 MAC、共享 Vector32 原定义、数值顺序/精度、五块 M128 刺激及所有资源/时间预算不改。完整模型数值/最终同刺激 RTL 仍 0/5，FULL 所需工程预算仍待实际进度证据。

## 2026-11-01 02:35 UTC：云端导入故障恢复（源码候选，尚未新执行）

- 原 executor `5214a22` / builder `e01529` 实际云端任务已完成 70 个权重（3,531,306,272 字节）和五块完整 M128 官方软件参考；五参考基线/观测输出严格相等，未运行硬件。控制器随后因 `numeric_tail` 的 sibling `live_budget` 导入路径缺失退出 1；不是数值失败、资源超时或构建失败。
- 最小修复仅受控、逐源码 hash 核验的 numeric sibling 导入，并用干净 subprocess 的真实模块导入回归，避免 mock 掩盖接线错误。
- 恢复使用新 executor 身份及独立预算输入。原 70 权重和五参考全部按原严格 native/cleanup/EOF/argv、冻结配置/来源和实际文件 hash 重验；原 receipt 仅作为数据/软件参考来源，不冒新安装、新参考执行或 DUT PASS。原 runtime / archives 仍重新执行当前身份下验证，旧 owner lease 不迁移。
- 同一 4096 MAC 硬件、原 ELF / SV / driver、数值参考算法和 PyTorch 路由不改；不重新 build、不重复下载本次已核权重。保留失败任务完整证据；所有权重、参考、NPZ、原始日志仍不上传。
- 五块模型完整数值及最终 RTL 均 **0/5**。每块 300 秒仍为有界诊断；FULL 工程预算待实际 DUT 速率/内存结果形成，不表示用户尚未授权完整验收。旧 unknown owner 5 GiB、DUT 2.5 GiB、consumer 512 MiB 与原磁盘/阶段门不扩。

## 2026-11-01：实际构建包接续云端执行（host-only 适配，非数值通过）

实际 build-only run 41257805047 成功，七件 artifact 13064009898 已按授权下载、逐字节验证。原 e01529 硬件/driver/ELF/SV 不重建不改写；执行端采用独立真实源码身份与受审完整 catalog 差异。修复 Make recipe 双空格误拒，并将官方精确恢复的原 builder loader/六库置于 workspace，仍要求静态与真实启动 resolved 全部原 SHA；不使用当前系统不匹配库或放宽 ABI。尚未运行 loader/DUT，源码测试与静态字节匹配不能当数值通过。

五块完整 M128 / 最终 RTL 仍 0/5；下一阶段沿原五 profile/runtime/reference/provider/consumer 链做真实资源准入后的有界校准，FULL 所需时限保持待实测速率。原 fixed4096、FP32/BF16 舍入与路由契约不变。本工作不认证 Vector 全链 II=1。

本日云端只清理 341 个有完整已核副本的旧 JAR 缓存和已验证七件保留副本的原下载 ZIP，实际回收 612,630,528 B；保留所有唯一证据、tracked 旧仓库、权重、runtime tree 与 unknown owner 5 GiB 预留，无第二次清理。

## 2026-11-01 00:36 UTC — TEMP：七文件传递已批准，恢复唯一 build-only 构建

用户00:35:33明确批准模拟ELF、同源SV、driver与4份metadata经GitHub Actions传入本云；不再重复询问同一范围。新增固定批准清单hash与guard/export精确绑定，原single-A/direct-parent/attempt1及9000s job / 7200s含prep构建预算保持。源提交不含launch；只有随后唯一激活会构建，不在GitHub跑完整验收。下载后先ZIP完整清单/sha/大小和静态readelf、资源审查，不对未准入ELF调用ldd/执行。不改硬件4096、C++、参考或精度。

当前SOURCE-ONLY：许可门解除不代表构建或数值通过。五块M128完整数值0/5、最终同刺激RTL0/5；实际ELF/ABI/运行资源仍待本次真实构建产物核验。

## 2026-10-31 14:17 UTC — TEMP：GitHub 构建 / 本云数值执行分层（源码候选，未启动）

用户明确 GitHub 不做完整验收；same-job 是原项目实现限制，不是用户要求。新增独立 cloud executor 身份/批准预算/完整入口，复用原 providers、原参考、完整 M128、严格逐项验收与 cleanup；builder 原六字段、七文件真实产物 SHA 和 executor PID/boot/UUID 分别绑定。GitHub 源码/构建 PASS 不计五块数值 PASS。

- **SOURCE-ONLY / TEMP**：321 项 normal 与 321 项 `-O` 轻量/合成回归通过；包含真实Python入口的fresh/reuse分支接线、原验收谓词和完整新owner合成链。新GitHub build-only及只读runtime复用分支已接入；仍仅源码资格，最终发布待独审。
- 完整 4096 Matrix MAC、同一五 profile 硬件/接口/容量/SV/ELF不变；本split不新增或认证Vector32全链II=1/性能，实际共享32-lane bank及其他ALU保持原冻结源码；原 FP32 顺序/每步 BF16 舍入、Qwen2 FP32存储、原 Torch 路由全部保留。
- 云端不机械继承 CI 21000 秒。Operator 批准的独立预算和输入 SHA 必须先到位，生命周期有限、逐阶段真实资源检查；FULL 还需实际校准/独立预算依据，300秒校准绝不冒完整执行。
- 低内存仅诊断候选：group RSS 采样 ≤2.5GiB、DUT hard AS ≤2.5GiB、consumer soft512MiB再于fork后hard512MiB；原1GiB非DUT余量与未知owner5GiB预约均保留。安装/参考同类受审角色低限不得改变数值/线程/数据；不足记 INCOMPLETE。真实ELF静态映射与父进程清单未审前不启动。
- GitHub build-only复用原7200秒含prep预算、150分钟workflow；审批硬锁仍None且无新launch。原地runtime先35B再Qwen2/0.8B fresh验证，不重用旧PASS；每次lease前后仍核原完整树。
- 七文件构建包中转未执行，不上传 weights/NPZ/input/reference/IR/classes/rawlog。runtime/archives优先复用已存在官方pin bytes并生成本次 fresh 验证链，不能继承旧PASS。
- 当前 ABI 仍严格核实际 loader/DSO bytes；workspace重定位依赖尚未接，不以架构/SONAME同名替代兼容证明。
- 原校准 run41163215771 在CPU AVX512门早拒，无DUT周期/速率；五块完整M128 **0/5**、最终RTL **0/5**、完整block利用率未知。现无新job、无新数值PASS。

# 五类 block：原始 Chisel 完整 M128 数值后再 RTL 回放（2026-10-26）

## 2026-10-31 03:25 UTC：FULL执行模式源码接通，真实预算/宿主仍阻塞（TEMP / INCOMPLETE）
- 实际run41163215771在原AVX512门早期拒绝，未runtime/build/DUT，没有可填full预算的速度证据。共同硬件不要求宿主CPU ISA相同，但原参考/ABI门不能无验证替换；合规固定云环境待用户/资源路径解决，不随机重抽runner、不降门。
- 新Python模式已接原prepare→flow→numeric_tail→consumer→原逐块严格验收→safe summary。FULL必须显式独立已审五份wall/maxcycles及实际calibration/review pin；接受SHA保持None、模板全null/ready=false，不能直接启动。calibration仍原300秒×5；FULL不继承无条件300/20000，也不把timeout当完成。
- 内层consumer保持原execute/Popen/清理AST及1/2返回；外层全5同artifact严格PASS才FULL transport0，明确exact mismatch为1，timeout/未到输出/缺state/缺profile为2。summary核固定根binding、源码pin、预算admission、每report实际mode/effective limits，再逐receipt重聚合，不能换label迁移cal结果。
- Chisel/C++/硬件/数据/参考/舍入/ABI字节未改；原冷M128 chunk路径保留。新增Python源码身份仍需未来同新source一次共同build，不能借未产生的旧binary。当前仍是Chisel发射IR/SV模拟，不是冻结后独立最终RTL；五块完整M128和最终RTL均0/5。
- 原21000秒及资源caps不增，现非DUT预留18000秒，五full窗口至多合计3000秒并须满足实际剩余首步时钟，未保证能完成。完整block周期/速度/比较耗时依据未有，利用率仍UNMEASURED；预算填值与实际启动留待真实证据，不继续空转资格任务。

## 2026-10-31 02:55 UTC：已审 SV 观测基线接回原五块生产链（TEMP / 待真实校准）
- 以 d339 实际证据提交为基线合入原隔离 production 候选：不覆盖新扫描器/投影器；旧 canonical/C7/85口历史原样保留。实际 run41159843264 proof f88769ed…及独审598ff33f…、summary dfacbbe2…被门逐文件固定哈希读取。ready 只表示限定观测 SV 基线已审，可继续原后端构建，不授予数值或最终RTL通过。
- 为避免300秒仅有reset样本，本包经授权仅调整driver只读日志调度：首个while成功step立即running，后每64 activecycles检查steadyclock且至少1秒才再输出；原DUT step/while条件/算术/ABI不改。safe summary复用原Popen/outer cleanup，输出有限进度及事后日志hash，未绑定/无active则null；外层elapsed除速率非即时仿真率，SIGKILL不保证最终帧，正式C++编译仍待同一次build。
- 原主链不重设计：35B runtime先装并严格清理→单次共同build→其余runtime→owner/weights/5份独立参考→五块M128同刺激。同一4096 MAC固定硬件/122口/新SVhash ec70…；下一fresh host重新检查Python3.12/x86_64/AVX512f以运行全5，不迁移旧host或16-lane结果。源码资格与真实archive/link/GCC双头依赖/运行资格分开。
- 当前实际入口仍只有每块300秒BOUNDED_CALIBRATION，21000秒总限及19500秒预留不变，不是完整执行mode。校准需导出原driver已有HOST_PROGRESS的实际周期/调度/速率证据；无完整block总周期依据时明确unknown，不把部分区间利用率当4096资源完整block分母。FULL_BLOCK_ACCEPTANCE模式尚待实际校准预算证据后最小接入，不能无限重复资格壳。
- 当前后端会发射IR/SV并编译仿真，属于原Chisel生成模型的数值执行链，不是纯Python/Scala行为模型，也不是冻结后的独立最终RTL回放。完整五块M128数值仍0/5，最终同刺激RTL仍0/5。源码提交不包含activation实体；实际执行待独审、CI、资源及冲突检查。

## 2026-10-31 02:48 UTC：真实两模块61-bit限定SV差异证明 PASS（非数值）
- 实际run41159843264成功，source c312f2ee、launch b845ae54；两原样安全回执及独审见 candidates/observer_sv_only_20261030/evidence/run41159843264/。15阶段严格native0、errors0、cleanup/EOF/gzip均真。
- 旧/新全SV normalized6555ede3…/ec70f911…与既有身份相符。Router仅8端口/4直接assign、Dense仅4端口/4直接assign新增四字段61-bit；删除规定增量后实际剩余normalized bytes分别179237/44477654双流逐字节相等。92模块顺序不变，82未变+8既定observer修改+2本次限定证明，无额外模块变化。
- 这是完整实际SV窄差异证明，不再仅toy/源码推断；仍不声称一般逻辑等价、五块数值或RTL回放通过。此前三次失败历史保留，不倒改为PASS。生产门接入需独立复核，本证据不自动re-pin。
- 原180秒scanner/300秒projection及3小时总cap未增加；未跑Verilator/GCC/archive/link/数值。五块完整128-token数值及最终RTL仍0/5，接下来回到同一统一4096硬件的五块主线。

## 2026-10-31 02:18 UTC：官方实例FileInfo布局修复（TEMP / SOURCE-ONLY）
- 实际run41156443649终态FAIL，前14阶段严格完成，projection75.173秒/native1。已取得真实有限拒绝：old / TransposedDenseDownOwner / PROJECT_MODULE / REJECT_NEW_KEY_REMAINS_IN_UNPROJECTED_LOGIC_PORT；旧Dense归一化hash e07f04…与两边whole/canonical本次真实绑定相符。471600行/44477644偏移是旧诊断EOF残留，不可当真正拒绝位置。
- 官方同布局小AST仅把WDefInstance NoInfo改为FileInfo，实际emitter在banks实例首行产生SourceInfo尾注释，使旧START正则不匹配，复现old/new Dense误拒。此是可复现解析缺陷，不是声称已读取本次真实SV实例行或确证唯一根因。279源端口上界小于4096，不扩cap。
- 修复只额外识别原b49c SOURCEINFO.fullmatch认可的首行尾注释，所有注释/实例字节原样保留；fixed实例/4个标签offset/精确表达式及全部剩余字节比较不变。任意注释/pragma/伪SourceInfo仍拒。官方小fixture最终旧新残余bytes直接相等，不继承完整SV通过。
- 有限诊断新增classifier分支/5计数及饱和标记；最终未豁免标识现在记录真正occurrence offset/line和有限类别，无raw token/body/log。原reason仍保留，失败不授权re-pin。
- 原15stage、180秒scanner、300秒projection、10800秒whole及所有硬件/删除判据不变。源码提交不运行重job；新fileinfo唯一nonce待sourceCI与冲突检查后单独激活，前三nonce不复用。
- 五块128-token完整数值及最终RTL仍0/5；真实SV证明未通过，不能由toy或CI绿灯更新生产基线。


## 2026-10-31 01:37 UTC：实例命名端口标签误拒修复（TEMP / SOURCE-ONLY）
- 实际scanfix run41153553582终态FAIL：前14阶段严格成功，旧/新SV扫描42.023/36.121秒；最终projection35.040秒/native1、supervisor errors空、清理EOFgzip完整。非cap超时；child拒绝谓词当时未导出，具体真实原因仍未知。不能把toy复现当实际失败原因确证。
- 官方FIRRTL DefInstance小AST复现原projector错误：既有child命名port标签被当parent同名信号，Dense旧/新都误拒。严格exact TransposedDownDenseBanks banks实例分类仅豁免4标签offset，不删除/重写其字节；真实连接表达式、member/hierarchical、其它实例/类型、条件程序或未知语法仍拒。原四field删除规则与全部剩余normalized bytes逐字节比较不变。
- 最终候选在官方exact实例toy经原scanner归一、旧新残余bytes直接比较相同；普通reg/memory toy排除了部分猜测。不继承真实SV通过；源码测试精确范围见发布manifest。
- 失败诊断保留有限reason/phase/module/side/计数/哈希，未知为null，超界有饱和标记；无SV/body/token/rawlog。失败native1永不授权re-pin，严格导出将exporter独立输入证据与child已观测区分。
- 原15阶段、scanner180秒、projection300秒、whole10800秒不增；无Verilator/GCC/archive/link/weights/DUT。源码提交不启动；新portlabel唯一nonce待独审、source CI与无并发确认后激活，旧launch不复用。
- 完整五块128-token数值仍0/5，最终RTL回放仍0/5；只有真正完整SV差异证明核验后才能审后续production门，不能由CI绿色自动re-pin。


## 2026-10-31 01:00 UTC：SV专项扫描失败修复（TEMP / SOURCE-ONLY，未重新实测）
- 用户已明确批准本次最多3小时的SV专项；原run41151061202终态FAIL，前7阶段native0/严格完成，old_svscan 182.287秒、native_exit=null、error_count1，清理/EOF/gzip完成；与180秒限时一致，但未保存错误类型，具体原因仍未知。新版与投影未开始，禁止继承PASS。
- 单遍修复仍调用原b49c scanner：完整LF终止模块的原digest同时更新module/whole hash，严格连续覆盖与终态code证明；不改scanner字节、旧新canonical/SV期望、61-bit投影判据、硬件或预算。合成34,998,998B/96模块实测旧18.012秒→新9.236秒、全部元数据相等；仅合成性能，不是实际92模块证明。
- 安全摘要V2区分expected/observed，失败observed=null；错误只输出固定枚举和CPU观测，不泄露日志原文。source轻测通过范围以本次发布manifest为准，不代表真实SV接受。
- 原launch已消费；新唯一scanfix nonce只可在修复source CI成功、无活动重任务与直接parent/single-A校验后启动一次。源码提交本身不启动。原15stage caps与whole10800秒不变；无Verilator/GCC/archive/link/weights/DUT。
- 主线五块128-token完整数值仍0/5，最终RTL回放未通过；SV接受/生产re-pin继续阻塞于实际两边whole/module哈希与严格字节投影结果。1024/1224未澄清不阻塞128。


## 2026-10-30 — SV-only 严格差异取证候选：TEMP / SOURCE-ONLY，未激活

- **DONE（仅源码/轻测）**：独立fresh CI旧/新完整155源码、各7helper、既有完整original IR→canonical→emit SV→scan→两模块严格差异证明入口。专用source pins 664项，SHA256 `7e7681939364073d9d236d51b06608fbf2bc90f9cf36a8256f6340ef545e2413`；normal/-O各53项轻量测试通过，含真实project_proof合成链及失败双artifact出口。它们不是实际全SV证明或数值通过。
- **ONGOING / TEMP**：保持旧/新canonical `90464ff…` / `00897fd…` 和whole normalized `6555ede…` / `ec70f91…` 硬锁；只审核两额外模块的61-bit key四字段端口及直接转发，其他normalized字节须严格一致。无自动re-pin，后续真实证明仍需独审；当前全SV整体re-pin继续暂缓。
- **TODO**：先核新source远端及CI，再另一个仅新增唯一launch的direct-parent提交激活一次；本源码提交不触发。原class不搬、本地未知owner84990不触碰/重试。仅JDK/JAR和SV-only，不含serialVerilator/GCC/providers/archive/link/weights/reference/DUT。
- 15阶段wall6360s+cleanup450s+parent900s=内部7710s；GitHub step129min=7740s只取整30s，workflow保守9060s，whole10800s余1740s。原phasecaps最大RSS6GiB、freshhost至少7GiB；保留原bootstrap更紧AS/log caps及whole repo+work的100k entry总边界。
- 只导出两份各≤64KiB的proof/summary及固定字段runtime身份hash，不导出rawSV/IR/classes/o/log/weights。CPU/runtime及最终数值资格不由此继承。五块M128完整数值仍0/5，最终冻结同RTL回放0/5，利用率未测。既有实际frontend/122 ABI/单TU限定证据及下方历史正文完整保留。


## 2026-10-30 20:34 — 实际 frontend/ABI/单 TU 限定资格通过；SV re-pin TEMP 暂缓

- source `a06b51416090fce2ad3d04336c82a5b7a2d00b97`，launch `50f2e807f28f11e80ffc418461da94fe1ba3c80b`，run `41118989254` SUCCESS；24阶段严格终态/cleanup/EOF/gzip/native0，完整4096 MAC不变。证据：`candidates/observer_frontend_qualification_20261030/evidence/run41118989254/`。
- **DONE（精确范围）**：实际 frontend、122-port header ABI（旧85不变+37观察输出）与真实 GCC 单 driver TU ET_REL / `.d` 依赖资格；不是 archive/link、DUT 或数值通过。host frontend 382.55016183s / RSS9596760064 B；driver TU 9.280295733s / RSS282021888 B。CPU avx512f=true只观察，runtime_qualified=false。
- **ONGOING / TEMP**：92 SV模块82 normalized相同、10改变，含额外 `Public21QkvReductionRouter` / `TransposedDenseDownOwner`。61-bit key / SourceInfo路径仅候选解释；尚缺绑定实际旧新hash的严格差异证明，整体SV re-pin不批准，旧production门保留。原metadata继续OBSERVED_UNREVIEWED，审计acceptance_authorized=false。
- **TODO**：先完成最小SV-only proof方案与独审，再决定正式生产全五块执行；未启动新job，不重复完整frontend。五块128-token完整数值仍0/5，最终同冻结RTL回放0/5，利用率未测。维持4096资源/同硬件、舍入/路由契约和原预算；不继承旧16-lane PASS或拿IR替RTL数值。
- 本包5项normal/-O测试仅合成审计资格；真实结果另由原2JSON及644闭包复核。只发布有界metadata/pins/脚本，不上传rawSV/IR/classes/o/rawlogs/weights。


## 2026-10-30 19:50 frontend-only / 真实单 driver TU 接线（TEMP，尚未 activation）

- DONE / SOURCE：基于d5cc9ff7501c9b99eeb17b03df20006604341bc7，将已实测IR的canonical/122口证据用于独立frontend-only候选。旧baseline原件保留；沿原155源8观察覆盖、完整4096 MAC、同一五profile硬件定义，不按模型重elaboration。16文件源码包manifest SHA446706d8244debedecf1d196dade84fcd47906f1804619f106b62ffa299995e8；专用644 pins SHA99adde3413b505b67ee68939e992f6e11eb50274662a1042417ce8121b5797c8。详见[候选范围与预算](../candidates/observer_frontend_qualification_20261030/README.zh.md)。
- PASS精确范围：21项core＋14项wrapper/export＝35项normal/-O轻测，YAML/bash语法通过，均source/synthetic；不证明实际frontend或driver编译。两个变更Scala helper＋五个纯AST依赖实际小编译native0：14.637411039秒、观测RSS272748544 B，strictcleanup/EOF/gzip完整，原RSS1GiB/CPU60/wall90限内。本次小编译没有编译155源、elaboration、生成SV或运行数值；[受控证据](../candidates/ci_frontend_pipeline_r2_20261029/OBSERVER_HELPER_COMPILE_20261030.json) SHAaeb84b01d7dd2c1a48fd446a08e7bff5337b8c8f9773cef22f0c683d03185a55。
- ONGOING / TEMP：候选只允许原HIGH→精确canonical与原变换→SV及完整normalized/module-fingerprint观察→串行Verilator frontend→真实header完整122口对照→Make严格语法和真实单GCC driver TU .o/.d。depfile必须来自实际-MMD且含两个观察header和sparse header；ET_REL对象不是host binary。明确不做archive/link、权重、reference、DUT或数值运行；新SV身份仍OBSERVED_UNREVIEWED，不能自动重pin接受。
- 预算逐层绑定同一首步monotonic起点：whole job21000秒；inner12000（16 stage wall11100＋cleanup480，余420）；prep预约2880但原aggregate1800更紧动态截止仍保持；3个parent metadata共900，执行step15780秒，含clock/checkout/guard/export/upload的声明envelope17100，whole job余3900。动态剩余不足即拒绝，不承诺各阶段最坏值都可用满；原supervisor/caps不放宽，资源不足不缩硬件。
- 发布只含两个白名单metadata文件，总≤2MiB（summary≤64KiB、qualification≤2MiB−64KiB），包含必要真实Make/dep文本及严格来源，不上传IR/SV/class/object/ELF/rawlog/系统header库存/权重。P0 avx512f仅原exact-token能力布尔观察，不承诺runtime/参考CPU资格，不改变profile策略。
- TODO：源码与CI/交叉审查确认后，另作唯一source→单文件activation（observer_fixed4096_frontend_make_driver_20261030_once），目前没有新重型运行。实际SV/ABI/Make/.d需再次独审才能推进共同backend及完整数值；原IR成功不迁移成frontend通过。五块128-token完整Chisel数值仍0/5、最终冻结同刺激RTL0/5、有效MAC利用率未实测，80%/90%目标保持，无本轮数据清理。


## 2026-10-30 19:37 实际HIGH/LOW描述符与8源差异审计（PASS仅限IR结构，数值仍INCOMPLETE）

- DONE / 实际IR：run41114764250，source975556/launch ec198，九阶段native0/error0/complete。统一155源8覆盖完整编译134.383487633秒、原HIGH/official LOW210.570589043秒、descriptor29.056340970秒；原严格cleanup/EOF完成条件保留，不继承旧run结果。原四份bounded metadata见[本次证据](../candidates/observer_ir_only_20261030/evidence/run41114764250/README.zh.md)。
- DONE / 独立源码与差异审计：1056模块顺序/集合相同，精确8个预期观察相关模块变化、1048项canonical hash不变。实际LOW122口，旧85口name/direction/type/width不变，新增37只读output（27/689bits＋10/259bits）。源码仅观察直连和互斥assert，无原ready/算术/状态反馈；不是整体电路语义相同，也不是generated header通过。
- DONE / annotations事实：实际9022条（9021 DontTouch＋1 TargetDir），旧8985内容与相对顺序保留，增37Top观察target。已pin历史文本重构1358737B的raw/ordered双hash与本次实际run一致；partial旧V1仅文本来源，不继承终态。发布重构脚本、pins及摘要，不上传annotation正文/IR/class。4项synthetic审计测试normal/-O只验证拒绝，acceptance_authorized始终false；限定GO来自真实metadata和源码审计。
- ONGOING：独立新canonical/LOW基线可引用本次observed-canonical.tsv（SHA00897fd49e82036e04195ef6fe2a671e0a3fd948d968de3e47c4dfa7388f6b5c），旧baseline原件保留。当前原metadata的canonical_pass=false/OBSERVED_UNREVIEWED保持，后续必须显式完成新严格接受gate，不能自动repin任意输出。
- TODO：新SV normalized/module fingerprints、实际Verilator header/GCC依赖、新共享backend数值仍未验证；当前ad299只是完整执行链source/mock接线。五块M128 Chisel完整数值0/5、最终冻结同刺激RTL0/5，固定4096 MAC与同一硬件/RTL要求不变，有效MAC利用率尚无实测。本轮未删除临时数据。

## 2026-10-30 19:25 五块 M128 真实消费者与运行来源链整合（TEMP / INCOMPLETE，未数值 activation）

- DONE / SOURCE：将已发布 P0 SRAM gate/up 和 MoE 实际 selector 输入/输出观察源码、统一155源的精确8项覆盖、R2 driver/headers及只读官方参考观察器接入实际 execution closure。真实调用仍为 numeric_tail → provider.prepare → connect_owned → consumer_owned，不是停在祖先run_compare或独立资格外壳。所有五profile共用硬件定义与后端来源，原4096 MAC、FP32/BF16顺序、原PyTorch路由不改。
- DONE / SOURCE：必要完整128输出/cache/state及已定观察逐项判定，缺项INCOMPLETE、精确参考不符FAIL_EXACT_REFERENCE；consumer不提前声称其外层进程已经清理，dut_evidence以真实owner/group absence/EOF收据复核后再给单块资格。numeric_tail/flow/safe summary重验同一来源与五块聚合，eligible4不能冒五块通过。MoE raw FP32与Torch差异只诊断，内部同ID位传递另验，不新增容差或擅认小ID tie。
- DONE / SOURCE：P0来源合同只同步实际改变的6项源/driver身份，原输入/view/程序及20→18真实DDR观察修正语义保留；旧UNOBSERVED metadata不伪造新SRAM receipt。producer/consumer必须核实际GCC depfile中的两个唯一观测header、真实路径与审核SHA，不能仅凭自报已编译字段。
- DONE / SOURCE：35B runtime提前安装，通过原strict cleanup后回调一次原build，再装其余eligible runtime，之后owner/weights/reference/tail；原资源cap、monotonic总期限与预约保持，不把安装当Torch/model import资格。所有新顺序仍仅source/mock验证，原35B历史失败原因UNKNOWN。
- PASS精确范围：82项normal/-O轻测（51验收与完整尺寸mock接线、9独立safe-summary反例、14安装顺序/预算mock、8闭包/来源链）。629项完整source pins精确校验。mock字段不计入真实五块数值结果，源级测试不等于实际IR/ABI、runtime或硬件通过。
- ONGOING / INCOMPLETE：IR-only source975556 / activationec198 / run41114764250已按独立身份启动，真实canonical描述符、完整122端口及其审核仍待原run产物；新SV normalized/module identity、真实Verilator ABI和数值执行尚未完成。旧canonical/85口/SV接受锁未删除或随意替换，本整合批不提供新的数值activation，不影响该IR run的冻结源码。
- TODO：消费并独审真实IR descriptor，再以新产物资格更新严格canonical/ABI/SV链；完成同源新五块128-token数值后冻结输入/参考/配置与源码，再同刺激最终RTL回放。当前仍300秒BOUNDED_CALIBRATION运输模式，未冒FULL_BLOCK_ACCEPTANCE；后者完整预算待实测校准。
- 五块完整Chisel数值仍0/5、最终冻结RTL0/5，利用率未实测；80%/90%目标保持。临时文件清单复查，本轮无数据删除，不上传权重/NPZ、IR/class、原日志或唯一运行证据。整合细节见 [源码接入状态](../candidates/same_job_execution_20261030/OBSERVER_INTEGRATION_STATUS_ZH.md)。


## 2026-10-30 19:18 补齐后续真实锁所需 canonical / 完整端口证据（TEMP，未 activation）

- DONE / SOURCE：发现IR-only原先只导出hash/count，后续actual backend仍缺新canonical完整manifest，故18828不先激活，先补同一IR的只读描述符，避免再做一遍重IR。新helper直接调用未修改CanonicalHighGate公开semantic方法；只剥Info/TargetDir，顺序不改，实际module/annotation计数。HIGH/annotations exact roundtrip；无新硬件elaboration。
- DONE / SOURCE：原helper实际LOW-port提取经hash/marker绑定后用官方Parser读完整name/direction/type/width，85旧口逐一保持＋37审核只读观察输出；输入在descriptor前后及导出前复核。完整canonical.tsv与details/provenance为≤512KiB独立白名单metadata artifact，不截断为只有digest，也不上传IR/class/rawlog。所有资格仍OBSERVED_UNREVIEWED，canonical_pass=false。
- PASS精确范围：56项Python轻测normal/-O；两helper＋一个微型fixture driver真实编译7.608秒/RSS248766464B，3口官方Parser fixture1.763秒/RSS110387200B，均native0/strictcleanup/EOF。只是本地Debian Java源码/API微测，不是CI工具链、122口、完整IR或数值通过。
- ONGOING：新helper_compile/descriptor各沿既有300秒/3GiB/heap2GiB上限，9阶段wall3180＋cleanup285=3465，3600总预算留135秒；原监督与IR资源caps不变。源提交/CI/独审后才可用未消费r3路径另行activation，未重试原任务。下一步真实descriptor独审后接通新canonical/SV/ABI锁，不直接更新旧接受hash来冒通过。
- 五块仍完整M128、固定4096 MAC/同一硬件与生成RTL哈希；Chisel完整数值0/5、最终冻结RTL0/5，利用率未实测。P0精度合同与MoE原路由基线保持，未批准tie不视为已批准。无本轮临时数据删除。

## 2026-10-30 19:07 IR 目录计数范围修复（TEMP，源码未 activation）

- DONE / PASS（仅真实编译）：run41108031789 / source0719 / launch400a 六阶段均native0，新R2统一155源8覆盖完整Scala编译75.941635151秒、观测RSS1585991680 B。source guard41107649508与launch guard41108031875成功；实际IR运行失败，不能用guard成功替代。证据见[原受控摘要与归因](../candidates/observer_ir_only_20261030/evidence/run41108031789/README.zh.md)。
- FAIL / INCOMPLETE：original_ir 在execute之前因entry准入被拒，HIGH/LOW未开始。已计数19993项＋预留8项>20000即中止，不是完整目录总数。当前扫描仓库＋work，却沿用旧局部IR 20k门；修复显式对齐入口既有aggregate 100k条目门。根范围、预留8项、原supervisor/cleanup及CPU/RSS/wall/tree/file/log预算不变，不保证新准入必过。
- DONE / PASS（仅源码轻测）：新admission有限枚举摘要保留拒绝/不完整census/execute未调用的区别，44项normal与-O分别通过。专用618项闭包SHA256 1277341d821c7ed915b15e4c500d88c6696dab23ff62a923137421b92265e0af；active598未变。新唯一r3路径/nonce及guard/workflow同步，旧17路径保留并拒绝重用，本提交无activation。
- ONGOING / TEMP：先核源码提交与CI，再独立提交一次性activation，获取新R2真实HIGH/official LOW与接口证据。当前122口只是预期；原本地84990未知owner与唯一证据保留，不推断已停止，不触碰它。CI旧classes随job结束未作为可下载payload保留，下一新身份只能按pins重建，不能从摘要伪造复用。
- TODO：把真实P0 gate/up、MoE输入/实际选择输出、独立参考与原实际consumer接入同一执行闭包；完整输出/cache/state及必要观察逐项判定，不能以固定INCOMPLETE壳或子集绿色代替验收。新接受条件仍待源码实现/独审，原路由基线、未批准同分契约、精度/舍入规则不变。
- 五块P0 Qwen2-1.5B、P1/P2 Qwen3.5-0.8B L0/L3、P3/P4 Qwen3.5-35B-A3B L0/L3完整128-token Chisel数值仍0/5，最终同刺激冻结RTL回放0/5，有效MAC利用率未实测。固定4096 MAC与同一硬件/RTL哈希要求、80%/90%目标不变。临时文件清单已复查，本轮未删除数据；原始log/IR/class/权重不上传。

## 2026-10-30 18:30 原始 Chisel 观察接口的独立 IR-only 源码（TEMP，尚未激活）

- 新增独立入口，复用原监督/cleanup/lossless log、固定工具/JAR与原Diagnose空参数，只到统一155源8覆盖的完整compile和HIGH/official LOW，不进入SV/Verilator frontend/native backend/weights/reference/DUT。Verilator只准备原identity所需固定包，避免更改原fresh_host合同。此步骤补新接口证据，不替代完整M128数值链。
- 专用616项闭包以215f active598为底，仅增加8已发布统一观察源和10入口/workflow，逐bytes/hash独立核验；32轻测normal/-O通过，原supervisor字节未改。preflight在execute前一次只读census，超原cap/不可读不调用execute，预留8项；非原子，不宣称运行期连续上界。
- 总预算3600秒、阶段wall2580+cleanup225秒；IR RSS5GiB/480秒/CPU420、tree1GiB/file384MiB/log8/raw16MiB/entries20k保持。目标runner准入未实测，不预先PASS；不会因为全tree API观测不可用而放宽cap。唯一上传typed摘要，不上传IR/class/rawlog/权重/tensor。
- 共享exclusive组避免与原数值bootstrap并发争资源；unique guard要求后续单独activation、单parent/attempt1/source直接parent。本源码提交无activation，无旧run重试。215f source CI41106619735已success，dedup/CPU修复只source/mock资格。
- 新R2的122口只是预期，须实际发射后独立核验；旧local84990未知不迁移PASS，不触碰旧owner。完整五块M128 Chisel/最终RTL仍各0/5，利用率未实测，4096/80%/90%目标不变。


## 2026-10-30 18:21 可选去重权限失败与 runtime CPU 门修复（TEMP，未新启动数值）

- 本轮明确终态：run41096005966/source7bb/launchfd947在17:58:24退出1；原27个backend阶段全部native0、wall合计2985.197s，fresh-host native0/192pins，host_link已完成，共享ELF139950896B/SHA ce0bcb621646cb9286c4273d9cb819e42f1513a4b3084d0b7c76bd44ba83837c。仅build准备，不是DUT执行或最终RTL数值通过。随后optional dedup初始writer census的fd.stat权限错误，在任何artifact修改前退出；runtime安装/reference/DUT均未开始。原job日志和受控summary保留，旧35B安装失败原因仍UNKNOWN，不混作本轮原因。
- 修复：初始/首prelink扫描不可用只NO_OP，保留两份物料、零link、节省0，不假称writers absent；交易开始后扫描错误沿原rollback/recovery并继续抛错，不能伪称零修改成功。实际writer/hash/admission和未知错误不吞掉；safe summary拒绝COMPLETE+UNAVAILABLE等矛盾。36项mock普通/-O独立复测通过，没有读取受限FD、提权或改系统安全/资源设置。保留双份仍受原资源caps。
- 另修静态潜在门槛不一致：runtime_phase原本对全部runtime无条件要求AVX512，尽管外层已选Qwen35-only。现在仅qwen2保留原AVX512 exact-token gate，未知key与错误Python/架构仍拒绝；两个Qwen35原DEFAULT/thread1/taskset/offline wrapper字节不变。10项mock普通/-O独立复测通过，未安装/import，非真实nonAVX主机资格，也不是本轮失败归因。P0原合同不放宽。
- 合并后46项mock测试在normal/-O各通过，未触发实际proc扫描/安装/import。
- 本批仅源码及598项精确闭包更新，无新activation，不改算术、精度、同分参考或固定4096资源。候选R2观察接口仍未完整编译/发射。独立IR-only前置资源census正在审查，原supervisor不改，新的有界尝试需单独source/identity。
- 后续降低重复build成本的方案：原安装可前移并复用同一树，但install不等于Torch/model import；原budget/reservation需重排，两个旧Qwen35树约74.7k entries会纳入build的100k限制，必须实际准入，未静默扩大cap/改flow/新增probe。
- 完整五块M128 Chisel/最终RTL仍各0/5，有效MAC利用率未实测。16afe源码保护CI41103075571已成功。原本地IR84990 owner未知证据保留，不据此说停止或重跑；本批未删除临时数据。


## 2026-10-30 18时：真实 selector 输出与完整消费者接线（R2，TEMP / INCOMPLETE）

- DONE（源码/轻测）：除每token256项真实selector输入概率，新增8项真实 selection.out.fire score/index/rank/last；kind区分事件，feed/read状态互斥，无新ready/算术/调度反馈。collector直接写真实输出score和ID两份4096B文件，绝不以input[ID]回填。新259bits/10信号、Top122口仅源码预期；本版Numeric尚未完整编译或发射IR，不继承V1编译/112口/旧119预期资格。
- 修复采集语义：旧候选把input-link/排序数值检查当落盘前提，会丢失错误样本，已撤回旧collector GO。当前任意FP32位型（NaN/Inf/负数/±0/>1）均原样保存；数值异常只计数，协议/fault/覆盖才阻断。C++真实collector→Python reader合成negative证明错误bits保留，分别观察3个内部差异、6个全概率参考差异、8个selected参考差异；这不是硬件执行。
- actual consumer以active7bb原00bac基线合并P0 resident gate/up与MoE input/actual output/独立reference比较，保留原ffb1合同、host/ABI/pins/cleanup/calibration及INCOMPLETE/exit2。内外比较分开：hardware output vs hardware input[actualID]是内部一致性；同次官方概率及原官方ID形成独立软件参考。无clip/舍入修补/新容差或tie批准。P0旧consumer不能覆盖active更新。
- 官方观察器实际gate-only fixture一次native0：9.347591102s、direct-child RSS354574336B、native前后12项核验，原tuple/local身份与logits/IDs/weights逐bits不变。仅合成输入/权重的固定官方gate，不是完整block/reference；cleanup只按原reference supervisor finally stop/killpg/wait及postverify，不升级strict IR终结证明。
- 包装复建7个base/result SHA在normal/-O分别通过，existing-output/base/result/P0-header负例均拒绝；38项包内轻测加7项observer轻测通过。materialize准入采用显式检查，避免-O跳过。5份旧摘要/patch/test按原字节归档legacy_r1，Git普通移动保留c639历史，不删除运行输入/唯一证据。
- ONGOING：原run41096005966仍source7bb/launchfd947，17:57 API仍in_progress；本次不改其active pins、不增加activation。c639 source guard41100401245成功。新观察候选执行闭包、真实完整reference/DUT、全required-stage比较仍待接通；独立短CI仅compile+原HIGH/LOW的源码方案正审，未激活，不跑SV/RTL调数值。
- 旧本地IR84990缺终结证据且跨namespace owner未知，保留INCOMPLETE、不重跑、不kill。完整五块M128 Chisel/最终RTL仍各0/5，有效MAC利用率未实测；4096固定资源与80%/90%目标不变。


## 2026-10-30 17:36 联合真实 MoE 概率观察候选（TEMP / INCOMPLETE）

- DONE（源码/编译范围）：沿原 Numeric → Pipeline → RuntimeExpertLoop → Top 新增真实 selection.in.fire 的 FP32 softmax 后、topk 前概率只读 Valid tap，保留 P0 resident SRAM 观察，无 ready/算术/路由/调度反馈。每 P3/P4 全128×256项131072B，collector核序列/身份/fault及末拍静默。四 Scala 已独立审计，联合155源8覆盖完整编译 native0：118.871542250s、观测RSS1574649856B、862class17967658B，strict cleanup/EOF完整。源码见 [MoE观察候选](../candidates/moe_router_score_observation_20261030/README.zh.md)。
- 独立官方参考候选只在原 PyTorch forward return 观察实际 router_probs 对象，不修改 forward/topk/返回/算术。baseline输出与cache逐字节检查先于保存。7项 observer 轻测通过，并非真实 Torch fixture或完整参考捕获；P7/stride8与torch.softmax差异仅报告，不创设容差、不擅认小ID tie契约。消费者 raw-score compare 与 P0 consumer 合并尚未完成，不得只复制候选覆盖现有路径。
- FAIL/INCOMPLETE 边界：联合IR已启动，但环境重连后原session84990不可读取，无终结RESULT、LOW及finalized日志。保留partial HIGH和采样，1248输入pins（含862classes）完整；当前exec隔离PIDnamespace和可取得锁不能证明原Java已消失，禁止推断native失败、通过或停止。当前新增225bits/7ports、合计119口均仅源码预期，不继承原P0实测112口。原IR重资格未重启，需原owner/session终结身份确认。
- ONGOING：GitHub唯一R3 run41096005966（source7bb6641、launchfd947e0）仍按原身份观测；source CI41095793997及launch guard41096005880成功。它使用冻结旧观察接口，独立于本候选，不把local重连当CI停止，不重复build/CI。注册五块、四Qwen3.5 eligible、P0原宿主策略延期均保持。
- 复建资格：新候选按7份已发布base/result SHA在fresh目录重建成功，16项轻量测试通过；不含完整runtime、IR/class/tensor/权重/原始日志。未改active source pins，未启动新activation。
- 完整M128 Chisel五块与最终RTL数值仍各0/5，有效MAC利用率未实测，固定4096与80%/90%目标不变。临时目录本轮407项、磁盘约20GiB可用；保留partial/唯一证据及所有输入，未删除数据。


## 2026-10-30 17时：真实观察通路发射 IR，Python DSO 准入修复（TEMP / INCOMPLETE）

- DONE（精确范围）：P0 resident gate/up 真实 SRAM 只读观察候选已完成本地原155源/5覆盖完整 Scala 字节码编译，native0，120.928s，观测RSS1589428224B，861 class。原 DiagnoseOriginalHostMoePhaseV5 随后实际发射 HIGH 与 official LOW FIRRTL，native0，151.343s，观测RSS4318490624B，严格 cleanup/EOF。该候选仍未替换 active backend。
- 本次 LOW 独立解析确认112端口：原85个端口无删除/方向/位宽改变，新增27个输出共689bits。HIGH SHA256 0beb67704eca597275afea1aa688601996aca4ffb5dfc5e2fc728b17d6179afc，LOW f52a49582417a849ea3c0d63082c5e9bbdb117aec6d79993eacc783c917ddde3。只是实际IR/接口证据，尚非生成SV、Verilator ABI、数值或PPA通过；本地DebianJava也不迁移CI Adoptium资格。
- 结构勘误：原helper已有一个UnifiedVectorElement32BankV4及其32个HeteroFP32Alu后代断言，本次LOW也独立确认该bank的32个ALU。全可达图是81个该类ALU，不是全设计仅32个。P0 SiLU16-lane/GDN scalar调度不否定已有32-unit结构，也不能把结构当成统一32-lane持续II=1。8个Matrix endpoint是接口/层级证据，不单凭端点数证明内部4096 MAC实现。
- FAIL：唯一canonical R2 run41086843436（source8cae，launch2afa）在6项准备native0后，fresh-host以PYTHON_EXTENSION / ELF_DEPENDENCY_UNRESOLVED / EMPTY_DEPENDENCY_LIST退出1，cleanup/EOF完整。未进入backend编译、runtime/reference/DUT。guard41086843454成功。保留受控摘要，不上传原始路径/库存。
- ONGOING：修复已加载Python扩展被ldd报告statically linked时的零DT_NEEDED分类。只接纳已pin、已由当前解释器加载、ET_DYN、无INTERP、完整dynamic表且无NEEDED/FILTER/AUXILIARY/AUDIT/DEPAUDIT的DSO；其他空依赖仍拒绝。本地Python3.13实物复现与synthetic测试不能证明本轮CI Python3.12具体模块，后者仍UNKNOWN。根目录许可、P0原策略、算术、硬件与资源cap不放宽。新R3源码nonce与旧4份launch隔离，source先CI，activation另提交，绝不重跑旧run。
- PASS精确范围：本次合并139项轻量metadata/lifecycle/mock/合成解析测试在normal与-O分别全部通过，非目标host或DUT验证。
- TODO：接通未覆盖的完整数值观察与比较；新观察接口须建立新的canonical/SV/ABI资格，旧hash不继承。P0原宿主策略仍延期；P1–P4只进入显式四块诊断路径，不能冒充五块通过。五块M128 Chisel与最终RTL完整数值均0/5，利用率未实测，80%/90%目标未达成证据。
- 临时数据盘点：本次IR manifest为13项439001203B，目录实际14项752045501B，额外LOW副本同hash；保留未删。17:02云端可用磁盘约20GiB、MemAvailable约8.6GiB，无本地重型作业；不启动超内存完整C++ frontend，不提交生成IR/class/权重/NPZ。


## 最新源码批：分离 P0 阻塞与四块推进（TEMP，尚未激活）

- 基于 e5801897，复用现有 entry/flow/runtime/owner/numeric 接线。默认全五合同不变；新增显式注册五块、eligible P1–P4、P0 原宿主策略延期模式。选择四块不是 CPU 缺 AVX512 的观测，也不是实际执行/PASS；不伪造 P0 receipt，owner 拒绝 P0 lease。仅两个 Qwen3.5 runtime 与四份 reference/numeric 调度，原三安装/五块时间和资源预约上界保留。
- 新鲜宿主合同只允许在原 owning bootstrap 内完成具体工具/依赖核验后进入原 build。原 JDK exact vendor/version、GNU13/14、固定 Verilator/JAR/source/canonical/SV/ABI 保持；新增固定范围 ELF/Python/shell 身份、GNU 缺库拒绝、查询专用 JDK 路径及 stage 前后 alias 核验。不是镜像白名单或整个 OS 资格，不继承旧 PASS。默认无 flag 仍执行原镜像合同。
- one_job 的监督后 alias 核验是新代码，已同步三份 producer proof 及 consumer pin 链与 manifest，并从 UNCHANGED 列表移出，单独记录 reviewed delta。旧被拒 watchdog 未纳入，原监督实现/资源 caps 不改。四个固定 fresh-host receipt 路径只导出状态/枚举/hash/计数；缺失及无效明确未资格，不上传依赖路径、环境或原始日志。
- 资源标签勘误：vector_lanes=32 是既有 artifact 声明值，不能证明真实32-lane每周期issue。已核 P0 SiLU 16-lane 源路径，GDN另有32项bank以scalar游标处理；不据此推断整个设计仅16 lanes。summary 增加 DECLARED_ARTIFACT_TAG_NOT_VERIFIED_PHYSICAL_ISSUE_LANES 和 vector_ii1_verified=false。4096 MAC约束、全部硬件/算术/路由源码未因本执行器批改变。
- PASS精确范围：合并后94项轻量 metadata/lifecycle/mock 测试在 normal 与 -O 各通过；初次合并的旧global-CPU字符串断言失败已保留工具记录，并改为检验真实profile-specific CPU合同后重测。无真实fresh-host inventory/安装/build/DUT、无新activation、无数值或利用率资格。
- 下一步：独立审查显式四块/fresh-host启动配置和实际runner准入，不能重跑已消耗activation。另有真实P0 resident gate/up只读观察候选：当前本地155源仅五文件override的Scala typer已native0（55.46s，观测RSS892080128B、cleanup/EOF完整），但本地DebianJava21.0.12不同CI，未做插件后置阶段/elaboration/RTL；该硬件/ABI候选尚未接入本批当前backend，旧哈希不得迁移。
- 完整五块128-token Chisel/最终RTL数值仍各0/5；原35B安装原因UNKNOWN。临时目录已盘点，未删运行输入或唯一证据。


## 2026-10-29 五profile共享三runtime接线及provider检查点（TEMP / INCOMPLETE）

原selected materializer新增显式共享runtime lease分支：P0使用Qwen2，P1/P2共享原dense14e738，P3/P4共享原MoE42ca970；不是五模型混用一个framework。三实际安装树adoption核原wrapper/Python/固定侧车和完整import-root快照，lease前后验证且postcheck成功后才发布V3；原孤立安装模式仍保留。reference_command、provider算术/程序/完整权重、原BF16/FP32及Torch路由基线不变。

本轮真实provider复用既有已核参考（不是新reference执行）：7阶段native0，overall363.974s、阶段wall合计249.513s。RSS有缺样，内存峰值资格INCOMPLETE，不能将缺样零值或观察最大值当内存PASS/严格上界；原采样/失败证据保留。仅源码、pin、受控摘要发布，shared owner完整路径及runtime/权重/NPZ/生成payload不公开。

此处是runtime物料复用与provider资格，不是DUT数值通过；P0 gate/up仍REQUIRED_UNOBSERVED，五块完整M128 Chisel/最终RTL均0/5，350分钟全链预算/真实DUT速率及80%/90%MAC目标仍未证明。无新workflow/launch/build或采样重跑。 详见[共享runtime来源](../candidates/same_job_materialization_20261029/SHARED_RUNTIME_CN.md)、[adoption受控身份](../candidates/shared_runtime_checkpoint_20261029/ADOPTION_PUBLIC_SUMMARY.json)及[provider实测范围](../candidates/provider_only_measurement_20261029/README_CN.md)。

## 2026-10-29 P0 producer真实来源证据接线（SOURCE_ONLY / INCOMPLETE）

直接修改原producer：在真实host_link前拒绝旧driver .o/.d，仅原stage成功且owned cleanup完成后收集实际GCC -MMD依赖、对象/binary pins和原生receipt；pack创建NEW七文件artifact，保留原source manifest，补入真实compile/constructor/driver来源元数据。P0 consumer从同一artifact自动绑定本次provider程序，按实际选中的header依赖验证split-directory，不再依赖用户手工拼接或同目录猜测。

本次仅源码与metadata轻测，无新build、loader、DUT、workflow或launch。生产证据尚须未来经批准fresh build实际产生；不能回填run40862676969缺失binary或新来源记录。原20→18观察修正不变，gate/up继续REQUIRED_UNOBSERVED/INCOMPLETE；四个其他profile不得使用P0例外。FP32/BF16、Torch路由基线和4096/32硬件不变。完整五块M128 Chisel/最终RTL数值仍0/5，预算/速率及80%/90%有效MAC未闭合。

独立INSTALL_ONLY采样的四阶段均native0，阶段wall合计152.473s，三runtime与cache最终inode去重3,506,537,745B；未执行Torch/reference/DUT。最大process采样间隔12.176789747s（census12.123572151s），观测峰值不是连续峰值或严格上界；三runtime共根不证明五profile复制/参考/输出策略能满足预算。仅提交[受控安装摘要](../candidates/install_only_measurement_20261029/README_CN.md)与提取器，不含运行库、权重或原始进程信息。

详见[producer补丁及证据边界](../candidates/ci_frontend_pipeline_r2_20261029/P0_SOURCE_EVIDENCE_CN.md)。

## 2026-10-29 原物料链到 same-job consumer 接线（TEMP / INCOMPLETE）

新候选将原 selected materializer 的 runtime 安装、所选profile完整权重（五profile合计70张）、独立官方128-token参考及provider路径接到同job V3 consumer；保留V1原件，先核共同build身份与startup ABI receipt，再发布独立V3及消费argv。此处仅发布可复现源码，不替换现有生产入口、不新增workflow/launch、不运行loader、Torch或DUT。

原独立复审41个测试方法及4组phase前置拒绝（P1误带P0字段、SV/driver/source同长度漂移）仅是metadata/control-flow测试，不是五块数值回归。本次便携复测每模式46方法（14连接+6原物料+13 ABI+4存活量+9 runtime）另记，不与历史41相加。真实metadata核70张共3,531,306,272B；本地保留目录存活量不是fresh CI安装/解包/reference/output峰值。P0仍缺实际共享source manifest的12anchors映射、retained消费证据与split-header准入闭包，gate/up继续REQUIRED_UNOBSERVED；完整五块350分钟预算及真实DUT速率未闭合，不压缩硬件/专家/原限制以通过。

同job ABI只约束startup loader/library身份，later dlopen不在资格内。原R2构建binary已随job结束，不从摘要伪造可复用产物。五块原始Chisel/最终RTL完整M128数值均仍0/5，80%/90%目标无新实测。参见[接线候选](../candidates/same_job_materialization_20261029/README_CN.md)与[ABI/存活量账本](../candidates/runtime_abi_liveness_20261029/README_CN.md)。

## 2026-10-29 最新实测：共同 binary 构建通过，完整数值仍 INCOMPLETE 0/5

LOCAL_DATA R2 [run40862676969](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/40862676969) / source `10a30bcf614af2d11ea9aaf3e61469fafd9801dc` / launch `ef6a5fcd95ff643c3d6527f91e4a80e5a1c914a6` 于 11:53:08 UTC 结束 SUCCESS。**PASS 精确范围：固定完整4096 MAC / Vector32 源码重新生成、SV身份、四原生frontend、真实三子库/Host库编译及Host链接、本job内七文件冻结检查；不是 DUT 执行或数值回归。** 27个记录阶段均native0，watchdog reason为空，cleanup/日志EOF完整。没有缩硬件、替换算术或放宽原资源上限。

只上传受控summary artifact `12894603598`，48630B / SHA `dd4d06f325371ff3c9b96fc0ef56e44c43c81dccc7b4745d88b9d6fe61e039cb`。本job报告七文件366163598B，manifest1683B / SHA `6fbc78a408600d17c081f2fde8b70651499b15d3ff26d354b7ae7480475a7374`；**binary/SV/完整manifest与build receipt未上传，binary独立SHA未导出，不能独立重新核验该临时ELF，也不能声称原binary可供五job下载复用**。源码pack执行了ELF64LE和稳定hash检查；该执行结果不等于目前仍持有二进制。原R1失败与其具体文件UNKNOWN记录保留。

下一步只准备经审同一job内数值执行与受控hash/size摘要方案，避免把跨job不可用产物当可恢复输入；不为补hash而重复构建。未来新增摘要字段不得逆推本轮缺失的binary/tool/build-receipt哈希。公开七文件上传仍未获准，无新launch由本checkpoint触发。五块完整M128原始Chisel及最终RTL数值仍 **INCOMPLETE 0/5**；80%/90%利用率目标未变，无有效MAC RTL实测。详见[构建证据与范围](../candidates/build_only_r2_checkpoint_20261029/README_CN.md)。

## 2026-10-29 LOCAL_DATA 构建准入失败及源码修复候选（FAIL / TEMP）

原 run [40856253077](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/40856253077) / source `3185e082df78a59d42d8eb9a76a1afb5146c4e42` 于 10:41:59 UTC 在 `conditional_admission.py:113` 的后端编译准入处失败。22 个已记录阶段均 native0、watchdog reason 为空且 cleanup 完整；本轮重新通过 SV 目录规范身份 `6555ede3…` 和四个原生 frontend。随后 ValueError `previous compiled/dependency product`（36B，SHA `c7300115137928620cfee0cca32dbde94e706eca5d1f2c0734aa80585b99853a`）阻止 archive/link；**没有 C++ archive/link、binary 或数值通过，原 CI 具体 offending 文件未知**。仅摘要 artifact `12890164804`，summary 40969B / SHA `8fab13a8c67f858799980b3e4ac9e6d13baf9a7d783be38c7436e44e72951951`，无 binary/SV 上传。

新源码修正 blanket `.d` 拒绝：仅解析已知 native `__ver.d`/Top `__hierVer.d` 的单行安全 dependency 规则，路径和 prerequisite 绑定已有固定输入，冻结 dependency hash；继续拒绝编译产物、未知 `.d`、recipe/命令/续行/symlink/逃逸路径。保存的真实 native-only Down/层级小样例证明存在合法 `.d`，仅作语法兼容证据，不追认原 CI 文件身份，也不当新完整构建 PASS。新增有界 relative-path/suffix/hash 失败摘要。此提交仅源码及轻测；**不含新启动文件，不重试旧 run**。需后续独立审查新启动身份；公共七文件上传仍未获准，完整五块 M128 数值仍 0/5，硬件/算术/容量/资源上限均不变。

## 2026-10-29 BUILD_ONLY_LOCAL_DATA / NO_PAYLOAD_UPLOAD 范围补充（TEMP）

本轮候选只在单个 CI job 内实际 compile/link 并检查本地七文件；只导出 ≤64 KiB 的受控摘要。binary/SV/driver/完整 source/tool receipts 不上传、不缓存、不文本编码输出，job 临时文件不构成后续五 job 可下载产物。identity 的 artifact_name 仅为本地格式字段，不代表 GitHub artifact 存在；不得据此声称同 binary 跨五 job 回放已具备条件。公共七文件上传仍待用户明确决定，原公共提案保持未激活。源码发布与新唯一 LOCAL_DATA 启动提交仍分开审查；本候选不含启动文件。完整五块 M128 数值仍 0/5，编译成功也不冒数值 PASS。

## 2026-10-29 最新执行导航：frontend R8 已完成；下一步实际 BUILD_ONLY

R8 run [40838373693](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/40838373693) 的21阶段均 native0，完整4096/Vector32共享硬件的源码→IR/SV→真实物理provider frontend仅生成资格通过；**尚无C++完整compile/link、binary或数值执行，五块M128原始Chisel/最终RTL仍0/5**。实际Host峰值RSS9,596,116,992B，说明不能在本地7GiB上限反复重跑。下一步经审NEW BUILD_ONLY沿同源重新生成后，直接条件审查实际Host.mk/85port、冻结derived闭包，顺序编译三子库/Host库并链接同一binary，不再另起frontend-only资格任务。完整实测身份、失败保留、下一步界限见[交接计划](FRONTEND_R8_BUILD_ONLY_HANDOFF_20261029_ZH.md)。原80/90%目标及先模型数值后最终RTL回放顺序不变；本补充不迁移旧PASS或修改74条todo/ongoing/done账本。


## 当前候选补充：共享 Vector/Element 32-lane（2026-10-27）

**这是用户选择的下一候选方向，不是已实现或已验收的新硬件。** 计划为共享 Vector/Element 32-lane、每周期 issue（32 Add + 32 Mul + 32 RNE）；固定完整 4096-MAC Matrix 不变。五 profile 仍必须共用同一份新硬件、同一接口和同一 RTL hash，旧 16-lane 的有限叶级结果不能自动迁移。

- **速率账本不是性能测量。** 32-lane II=1 与 64-lane II=2 都是名义 32 lane-ops/cycle；资源较省只是选择较窄 bank 的设计目标，不是频率、面积或系统吞吐证明。已有纯理想事件模型假设固定延迟、免费输入/输出及无 DDR/其他 owner 冲突，不等同当前硬件执行。
- **必须改完整请求链。** 需要 issue/retire 分离、多 outstanding 的 tag/credit/scoreboard、有限结果缓冲及本地跨 tile cache。当前单 pending owner 不能据名义 II 声称持续发射；缓存槽数须按真实流水延迟、backpressure 与事务语义确定，不把模型中的三槽示例当通用充分条件。
- **算术语义不随位宽规划放宽。** 共享 exact FP32 RNE 流水 Div 需要独立资格，原 sqrt 能力不能删除；各 profile 的逐步 BF16 RNE 和原 FP32 中间值语义分别保留，不能将 Qwen2 FP32 gate/up 压成 Qwen3.5 BF16。统一数据 cache 规划至少 17 B/activation（FP32 gate/up 8 B、两个 FP32 work 8 B、k 1 B），32-lane 每槽数据 544 B；context/tag/flags/scoreboard、DDR ACK 缓冲、Div 流水寄存器及对齐开销另计。旧 13 B/activation 仅属 35B BF16 gate/up 案例，不代表统一五 profile 容量。
- **重新建立完整验收。** 五块可并行，但仍先在原始 Chisel 完成各自完整 M128 数值门，再冻结同份源码及各自输入/权重/官方参考/比较合同，生成并回放同一新 4096 硬件 RTL；不得借用旧 16-lane PASS，或以 leaf、mock、软件模型和理论 lane-ops 替代完整 block 数值与有效 MAC 周期账本。

### 当前代码与失败导航（不升级状态）

公开基线为 `d16001c4543b75455a0cb36a1fcd0908b9aef725`。最近的 [FIFO 模型小批](../candidates/retained_matrix_fifo_model/README_ZH.md) 只发布原字节候选、类型身份和历史严格 hash/form FAIL；它未给出 FIFO 24-edge 等价或 service 加速资格。[service 阶段观测](../candidates/retained_matrix_service_observation/README_ZH.md) 仍为 CPU120 FAIL、0/1 case：首个 reset-high `step(2)` 返回不证明后续 `step(3)` 已进入或完成，也不能定位热点。后继 formcheck 或修复门须绑定自身实际证据，不能回填旧发布范围。

norm 父链本轮 3/4 是三个协议 case（unsupported/held-memory-abort 与 DDR epoch late-reply 隔离）的局部通过；fullcontext/txn0 探针失败，整体仍 FAIL，不是 norm 数值、完整父链或真实 Admission 集成 PASS。txn0 Boundary 的统一合同修复候选尚待真实独立验收，不凭源码修改或编译成功升级。

本增补仅更新中文候选与派工导航，`doc/block_checklist.yaml` 的 74 条任务及 13 done / 14 ongoing / 47 to do 全部保持，历史证据与 FAIL/TEMP 不删改。完整五块 Chisel/RTL 联合数值资格仍未建立，完整 block RTL 仍 0/5，4096 有效 MAC ≥90% 未证明。下文各日期、当前字样和旧基线保留为历史时点说明；原始 Chisel 数值优先的顺序继续有效。

## 当前执行顺序：先原始 Chisel 数值，再 RTL 回放

按 2026-10-26 15:56:30 / 15:57:17 UTC 的最新用户要求，**五个 block 可以并行；验收顺序是原始 Chisel 完整 128-token prefill 数值回归 → 冻结同源、输入和参考 → 生成 RTL 并回放五块数值回归。** 五个 profile 为 Qwen2 L0、Qwen3.5-0.8B L0/L3、Qwen3.5-35B-A3B L0/L3；不能把单个 leaf、mock 控制测试或独立 Python/C++ 软件模型结果当作原始 Chisel 整块通过。

1. 保留并复用 Qwen2 已修 92 源的既有 prefill 能力：`HostBlockCommands` 的 public21 入口允许 M16/M128，`Qwen2Block` 已有跨 token 的 Norm/RoPE/Attention/SiLU FSM；它并非只有 M1。该代码仍受固定 Qwen2 shape 与内部算术约束，须接入五 profile 统一 runtime / 共享 4096 资源，并保留原 QKV 分段归约语义，不能以普通 dense 求和冒称等价。Qwen3.5 原始 block 适配入口的 M1 限制单独处理。当前补齐原始 `HostBlockTop` / `HostBlockCommands` / `QwenOwnerKernel` 到共享真实数据 owner / Matrix 与公共 runner 的统一接线、完整数值闭环；五 profile 并行且不互借 PASS。
2. 五块原始 Chisel 数值门通过后，固定同一份源码身份，并冻结各 profile 的输入、权重、官方参考及批准比较合同；不把用户指令或待执行配置记为已完成。
3. 再生成并固定**同一完整 4096-MAC 硬件、同接口、同 RTL hash**，只切换 runtime 配置与权重，回放同一批五块输入/参考。仍需独立 RTL 数值证据；Chisel PASS 不自动继承为 RTL PASS。

当前公开主线基线为 `56f4e11ed805f96dc2f1e50384cc7f832012bfca`。根 `chisel/continuous_prefill/` 的 455 个文件相对 `c590179c4c3424ded9997ba8f15f27821df304c9` 均为相同 Git blob/mode；这项裸根目录身份事实不等于上述已修 92 源 overlay 已被直接安装到根目录；后者按 [公开来源重组流程](../candidates/qwen2_ordered_vector_compile_evidence/README_CN.md) 复现，72 个公开 recipe 源加 20 个原 pin 的外部 HardFloat 源单独绑定。后来发布的 admission、state、GDN、MoE、共享 fabric/controller 候选也不能冒称已经接回原始完整 block 入口。本段确认既有源码能力，不新增任何 Chisel 数值 PASS。最新结构/ABI/Yosys前端结果只按各自范围收尾归档，不升级完整 block 数值，也不另开 EDA 主线绕过上述顺序。

此处只纠正执行顺序与导航，`doc/block_checklist.yaml` 的 74 条任务及全部 `to do/ongoing/done`、旧 FAIL/TEMP、固定 4096 有效 MAC ≥90% 目标保持不变。五块原始 Chisel/RTL 联合完整数值验收尚未建立；既有软件观测域或有限 leaf PASS 不回填该缺口。

## 历史 06:04 / 06:36 执行导航（顺序已由上节覆盖）

按 2026-10-26 06:04 UTC 的用户新要求：**继续核验当前真实硬件结构能否生成 RTL，同时并行推进其余四类 block；不再让它们等待 Qwen2 主线完成。** 旧文档中的“先 Qwen2、再其余模型”保留为历史时点说明，不再作为当前派工依赖。

**最新硬约束：直接验证完整 4096-MAC 配置。五个 profile（Qwen2 L0、0.8B L0/L3、35B L0/L3）必须使用同一份硬件、同一个接口和同一个 RTL hash，仅 runtime 配置及权重不同。** 不允许分别以 16/32 head 的 elaboration 生成两套电路再声称满足“通用硬件”。固定最大 32-head 容量、5-bit 索引与 runtime heads 的共享 state 控制叶已独审并发布（7bf6fc287ba9e7b5f696c44a691f432a3e3958c4）；仅同一叶实例 runtime16/32 控制范围 PASS，不代表完整 4096-MAC 五 profile 通用 top 已接入或数值验收通过。

此前单 512 endpoint 的 lint 候选已撤销且未运行，不能继续作为当前执行计划。旧按 16/32 分别 elaboration 的 state32 九文件方案已暂停，不随本批发布为解决方案；toy/DPI 冻包继续保持未发布。

| 分支 | 当前安排 | 本片授予的实际资格 |
|---|---|---|
| Qwen2-1.5B 典型 block | 真实 Matrix 硬件生成、provider 结构与资源风险继续收口 | 下述限定的重发射与源码重组；不是完整 block RTL 数值 PASS |
| Qwen3.5-0.8B L0 | 与主线并行核查源码、合同、测试及当前阻断 | 本片不纳入新的模型实际验收结论 |
| Qwen3.5-0.8B L3 | 与主线并行，单独保留证据和失败 | 同上，不借用 L0 或 Qwen2 结果 |
| Qwen3.5-35B-A3B L0 | 与主线并行，区分共享部件与完整 MoE | 同上，router 冷门通过不等于 MoE 实际通过 |
| Qwen3.5-35B-A3B L3 | 与主线并行，单独核查 Attention/MoE 合同 | 同上，不借用 L0 或单个 TopK 测试 |

本片是新的派工/证据导航，不改 `doc/block_checklist.yaml` 的 `to do/ongoing/done`，不关闭整体任务。完整 block RTL 数值验收仍为 **0/5**；固定配置下有效 MAC 利用率 ≥90% 仍未证明。软件 M128 的原观测域 PASS、有限 M1/M2/M3/M17 scripted 端点行为资格与旧 FAIL 均保留，不能互相替代。

## 已实际重发射：真实硬件未被 DPI 替换

新独立 CHIRRTL、SV 任务均自然 exit 0 且完成原锚定清理。独审对两个**新**产物完整流式哈希一次，分别与此前已审产物一致：

| 产物 | 字节 | SHA256 |
|---|---:|---|
| CHIRRTL | 19,551,779 | `bdfbf223cc8c1c8de8a8d21450272878d1422842bc17a452bcef45e9878573bc` |
| SystemVerilog | 48,274,540 | `c117e75ae97fb0a978e7cebe8e942a652bf1fbe927505d66092fa39b87380181` |

重发射使用已合格的 **557 个 class**，不是从当前 main 做全仓 clean build。选定硬件 top 是 `OrderedQkRealMatrixCore`；`OrderedQkRealMatrixCollection` 只是共同 namespace 的生成容器，不能冒充产品 top。现有结构为 38 个定义模块，仍有各 8 个 endpoint/clock-gate 外部声明；发射成功不代表 provider 实现已展开或综合。

尤其要区分：**当前 `OrderedQkRealMatrixCore` 是已限定的 Qwen2 局部结构，不是已经统一五类完整 block 的通用 top。** 本次同 hash 重发射只证明该选定结构可重复生成；还没有五 profile 共用完整 top/interface/RTL hash 的联合验收，不能用文案或五份局部测试替代它。

原算术 provider 保持 8×512=4096 lanes，仍走四个真实 HardFloat 位级模块，不是 scripted tile。13 个原 provider 加边界适配形成 14 文件 canonical 非 DPI 连接：一个 endpoint 仅改名，另一个 wrapper 处理原 22-port 边界；不能把它说成 13 文件完全未改，也不能同时列入两个同名 endpoint。toy/DPI/`m_seqnum` 试验不在此硬件输入链。

**本次新 CHIRRTL 实际仍有四条 W005**：对 Vec(256) 使用 4/5/6/7-bit 动态索引，工具预期 8-bit；本次新 SV 另有一条 `DedupGroupAnnotation` warning。原 0616 审摘要把 CHIRRTL warnings 误列为空，是其过滤漏掉 `[warn]` 格式；现由独立勘误 `3964215f370f9867e99f3786a5dc232a913995aca4416a5ba9b5f1521fdff63b` 纠正，本次与旧 924 B warning log 同 hash。原审 freeze、旧包及历史 warning 保留，不称 warning-free；既有局部 index 范围分析不升级为新完整数值或类型资格。本片不提交大 FIR/SV、class、JAR 或运行缓存。

## current main 的源码来源闭合

本次 source-only 重组绑定 `c590179c4c3424ded9997ba8f15f27821df304c9`，不是把旧 checkout 的 HEAD 当作当前 main。后继 router 小修 `e096dba9220747855223b26d04c2d339c19cb675` 只改三个冷门文件，没有改此硬件源链。

公开 recipe 路径及原字节 pins 在 [来源索引](../candidates/current_hardware_reemission/pins/EVIDENCE_AND_PUBLIC_REFERENCES.json)。从 main 的 preimage/patch 重组 72 源，加原 pins 固定的 20 个外部 HardFloat 源，共 92 源、999,643 B；另重组 6 个 donor provider。独审 fresh hash 98 件均与此前执行输入吻合，共 395 项重组检查。

必须保持以下区别：

- 根 `chisel/` 与 provider 裸文件是 preimage，不等于候选 overlay 已替换根目录。
- 92 源中 60 个有同字节 main blob，其余 32 个依赖公开 recipe 或外部输入；20 个 HardFloat 仍是明确外部前置，不声称整个执行闭包都已放入仓库。
- `replay_handoff.py` 原设计 `exit 2 / INCOMPLETE` 保留；后续 92 源 builder、`qwen2_ordered_vector_chisel/prepare.py` 和 `stage_inputs.py` 的 source-only 成功不把它改成全仓 PASS。
- 新重组树没有再次 scalac；独审也没有重复运行该 recipe、JVM、EDA 或算术目标。

## 资源与硬件验收风险

仅 lane 的 5×FP32 accumulator 与 5×FP32 result FIFO 就有 1,310,720 数据位；service 两个完整 16×256 FP32 tile 另有 262,144 位。两项合计 **至少 1,572,864 数据位**，尚未计 Core 本地存储、score/prob、控制和管线。这是源码容量小计，**不是综合 FF/BRAM/面积报告**，不证明 4096-MAC 配置资源适配。

有界同步 memory 不等于已绑定技术 SRAM；大 `Reg(Vec)` 也不会自动成为 BRAM。局部组合 ready cone 未见自环不等于完整网表 SCC 通过；有意 ICG latch、时钟停启/复位释放、真实 cell mapping、STA/CTS/目标频率 和物理扇出仍待验证。旧 4096 lint、全图 2 GiB RSS FAIL、no-plan 与 CPU 统计覆盖缺口全部保留。

历史 06:54 工具门序（已由文首 Chisel 数值先行顺序覆盖，不再用于当前派工）：后续门按固定原算术、完整 4096 配置及统一通用 top 合同推进：完整 provider 层次的前端/结构检查、综合与闭合 SCC、资源/时序，再做五 profile 的非零完整 block 数值和有效 MAC 周期账本。必须分别记录同一 RTL hash、同一接口及 runtime 配置；不能退回单 512 替代完整验证。本片不把这些待执行门写成通过，也不允许通过缩小 lanes、stub/blackbox 或静默更换算术来“通过”。

## 审核与范围

独立硬件审查：`8159839a9e4e50c41c6b3057601ae1f55be4f67297b04a4d67eb609bddf40cab`；冻结：`e36f413483370372cf5b9a5dbbc30abb1c35ea87e6d7307bb29394262197358b`。安全投影见 [SUMMARY.json](../candidates/current_hardware_reemission/evidence/SUMMARY.json)。采样 RSS 不是连续峰值；root 端点证据为 expected 列表与 source-bound pass，不声称逐项独立 observed digest 轨迹。

本片不含新的四 block 实际成果、共享 state32 修复或 TopK 测试，也不把下一工具候选写成已经通过。后续各自独审后再小批纳入，不等待全部五类同时完工才提交。


## 2026-10-30 同 job 五块 M128 接线（TEMP / INCOMPLETE，尚未激活）

- 新增唯一未激活 workflow 与 source/launch 分离身份校验；没有启动 manifest，本提交不启动重 CI。原被拒 watchdog 新版不包含，仍用已发布监督脚本。
- 真正接线顺序为同一 4096 MAC / Vector32 backend 构建 → 原 53 archives / 完整 70 tensors 单份 → 原三安装及 fresh owner → 五块 M128 独立参考 → 原 provider → 同一 ELF 五 profile 短 wall 标定。所有数据留 job，仅允许受控 ≤64KiB 摘要上传。
- 350min 首步骤时钟；19500s 有限停止预算，另留1500s。五个300s诊断窗口不缩M128/max_cycles，不能冒完整数值PASS。旧本地5/5 Python参考与历史build资格不迁移为新 job 通过。
- 前置需实际 AVX512/Python3.12/原image和JDK、MemAvailable13GiB、free20,671,240,864B；不满足明确NO GO，不改硬件或资源门。标准runner标称存储不保证此门通过。
- Source-only 审查及轻量元数据/mock测试通过；无真实新安装、参考、DUT执行。完整Chisel数值与最终冻结RTL仍0/5，利用率没有新实测。属于Chisel测试发射IR/SV仿真backend，不是最终RTL回放。
- 下一步仅在独立复核实际资源/唯一 activation 后开展受限标定；失败沿原身份诊断，不自动重复构建。MoE同分小ID契约仍待明确。



## 2026-10-30 原同 job run 41034072605：FAIL / 具体资源原因 UNKNOWN

- source0235a207、launch1ed8612f，attempt1，原任务已终止且未重试。27个backend准备/编译/归档/link阶段native0，阶段耗时和2516.52s；实际共同ELF139,950,896B，SHA ce0bcb621646cb9286c4273d9cb819e42f1513a4b3084d0b7c76bd44ba83837c。仅hash可验证，未上传/保留可下载binary。
- SV raw c8e6b1c8…、受限SourceInfo规范化6555ede3…通过，仅仿真backend身份资格，不是完整数值或最终RTL通过。Host观察RSS9,597,370,368B，旧采样监控不是连续峰值证明。
- archive、70tensor、Qwen2与08B安装native0；35B安装阶段27.43s，native=null/errors2，cleanup与日志EOF完整。原supervisor具体错误及tree/cap数据未被摘要导出，完整公开job日志也没有，故原因保持UNKNOWN，不能因两条error猜定磁盘超限。
- 本次owner/五参考/provider/DUT均未开始，完整数值仍0/5。实际安全摘要12,031B SHA77a70f8bf677342910de92c8995f2144f0da223aa252621f5b689ccc1fa4882e，原artifact12969717356只含摘要。
- 本提交仅补摘要typed reasons/原错误hash和长度/现有资源指标，并修64KiB降级时保留真实嵌套telemetry；6小fixture normal/-O通过。没有修改监督脚本、cap、硬件、数值算法、workflow或activation；不能追补已丢失的原reason。
- 下一步先收束保活磁盘证据和原路径引用，原2.462GB inventory仅obj，不代表总job；不得先据推测提高cap或盲目重跑。


## 2026-10-30 精确两复制物生命周期接线（TEMP / 未实际去重）

- 基于57ec657d新增固定SV/ELF两对复制物去重helper及20小fixture，接在原build完全终态后、材料前。只保留两端路径的同设备硬链接去重，不清理obj目录；原四P0 producer、4096 MAC/Vector32、数值算法、cap、已发布supervisor、workflow/activation均未改。
- 准入要求27原native完整cleanup/EOF、七文件和源身份/五archive-link receipt一致、两端hash/size、effective uid和gid相同、mode完全相等、初始单链接、无symlink及可见writer。三锁内重核journal；普通失败可回滚，foreign inode或无法证明的残留保留等待诊断。禁止chmod/chown，任一mode不等整轮NO_OP。
- 20临时小文件fixture normal/-O通过仅是源码/生命周期测试；未操作真实CI数据、未删除唯一证据、没有启动新CI执行。收益0至362,153,111B仅逻辑inode存活量，不是物理free释放或整体12.081GB适配证明。原ELF可能755而pack700，因而可完全NO_OP。
- 原run41034072605的35B安装错误仍UNKNOWN，不能把候选去重当根因修复。原任务不重试；完整Chisel数值/最终冻结RTL仍0/5，无新利用率实测。下一次真实执行仍需独立审查准入与有限预算，仅摘要出站。

## 2026-10-30 安装前后whole-root快照（TEMP / 未实际采样）

- 在既有install_job的三安装前后/finally调用原已pin live_budget.census；同一native锁下仅使用未预占全job剩余时间，保留原native/cleanup/bind/tail预算。原watchdog、cap、数值、workflow/activation均未修改，不增加执行壳。
- 固定6个安全label，记录whole job+repo inode去重bytes/files/entries/free/symlink计数和monotonic起止/耗时；20s为协作检查，不是OS调用硬限。后置只在cleanup/EOF完整时扫描，否则明确UNAVAILABLE。native失败但cleanup完整可观测；结果不是失败瞬间，也不是连续峰值或资源PASS。
- 快照每条4KiB，summary严格枚举/数值/hash投影，缺失/超限/巨整数等标INVALID_FIELDS，不丢原stage，64KiB降级保留；不上传私路径、argv、原错误全文或数据。17小fixture normal/-O通过，仅元数据/模拟census，不是真实安装或目录采样通过。
- 原run41034072605的35B安装原因仍UNKNOWN，不能追认旧缺失reason；该源码只改善未来获准执行的可观察性。没有新安装/EDA/去重/删除/activation，完整硬件数值仍0/5。

## 2026-10-30：新一次性同 job 诊断启动源码（TEMP，尚未启动）

- done / PASS（仅启动接线）：以 7c545226 为源码基线，将既有 workflow 与 guard 的单次路径/nonce 更换为 five_m128_samejob_diagnostic_r2_20261030_once；保留单新增文件、精确 parent/source/event、attempt 1、实际 run/blob 身份与所有资源门。对应三项 source pin 同步更新，其余不变。
- done / PASS（仅轻量 fixture）：7 项测试在 normal/-O 各通过；含真实两提交 Git 身份、旧 activation 文件保留、旧 nonce/path 及错误事件/重试/资源拒绝。无 backend/runtime/DUT 执行。
- ongoing / TEMP：先发布并验证新源码提交，再独立审核只新增新 activation 路径的一次提交，source_sha 必须绑定实际新源码。当前没有新运行身份，不能宣称已启动或资源门已通过。
- 原 41034072605 安装失败原因仍 UNKNOWN；27-stage backend 构建不是数值通过。修复后的 typed 诊断、安装前后离散快照与精确副本候选只适用于未来运行，不追补旧证据，不保证资源适配。
- 五块仍完整 M128、同一 4096-MAC/Vector32 backend；未来每块 300 秒仅执行标定。独立 Python 参考 5/5；完整 Chisel/RTL 数值各 0/5，MAC 利用率未新增实测。未修改数值/路由/硬件/caps/旧监督程序，未上传权重或运行 payload，未清理文件。

- 同批补充：安全摘要新增固定去重 journal 的六类枚举状态、逻辑节约量、receipt/build hash 和两固定 role 状态；不导出路径/用户标识/异常全文。新增14项与既有安装快照17项元数据测试normal/-O通过。journal产生前失败仍可能为NOT_OBSERVED；COMPLETE仅为journal声明，不是独立实际去重、物理空间或数值验收。原35B安装原因仍UNKNOWN。

## 2026-10-30 diagnostic R2 实际 NO_GO：CPU_AVX512（无重构建）

- source04be815f、launch718a451e，run41064855934/job124093486574/attempt1，已completed/failure；启动身份与checkout通过，主步骤在13:38:23Z因CPU_AVX512前置停止。没有材料下载、backend构建、安装、参考/provider/DUT执行，未重跑原任务。launch提交检查41064856103成功。
- 原始log的runner ImageVersion为20261025.353.1，亦不等于固定20261026.354.1；实际首个失败仅CPU门，不能声称后续内存/磁盘/源码门已通过。
- 唯一artifact12980938760为638B摘要ZIP，SHA72191129a1b4f94c586ba8fea4c915edd64e3d9151a09225af7cb55ce387279e；解包原摘要SHA77c91397c306fba7c583ffe821ea1def2c7e50de3c322ce5d0e0d790a4afdacd，stages空、numeric_pass=false、dedup NOT_OBSERVED。未上传payload。
- 下一步审核宿主CPU/工具版本绑定的真实依赖，不能直接删除AVX512或镜像门、盲目重试或迁移旧参考PASS。原35B安装原因仍UNKNOWN；五块完整Chisel/最终RTL仍各0/5，有效MAC无新增实测。

## 2026-10-30 P0 宿主 dispatch 实测（FAIL_BYTE_DIFFERENCE，非硬件）

- 未重试CI。当前本地AVX512宿主上，复用原runtime/官方forward/权重/刺激/FP32-BF16规则，A=AVX512四线程、B=default四线程、C=AVX2四线程。A/B串行，C独立新目录复用已核A；原V2 lease及监督资源cap不变。三捕获native0、cleanup/EOF完整，两个严格比较入口均exit1。
- 独立复核全部24项导出张量文件：A与原参考24/24逐字节一致；B与C均23/24。唯一差异为注意力概率stage.self_attn.0.1的196608个BF16元素中1个编码相差1，最大绝对差5.820766091346741e-11。最终输出和KV完全一致仍不升级严格中间张量等价；两试验均FAIL_BYTE_DIFFERENCE，不替换原参考、不修改阈值。
- PASS只限捕获进程完成、身份/文件哈希核验和相应相同张量；没有Chisel/RTL/DUT执行。ATEN AVX2不保证底层MKL/oneDNN不使用AVX512，本地试验不认证实际非AVX512宿主。只检查24个导出张量，不声称官方函数内部全部中间值已观测。
- 发布仅安全摘要、receipt/recipe哈希与策略差异；本地binding、运行库、权重和张量数据不出站。两套轻测分别7/8项normal及-O通过。源码/FAIL/原数据均保留，没有清理。
- 重执行仍缺符合原P0及具体工具身份的足额AVX512宿主；不能在随机standard runner上反复碰运气或直接删除CPU/image门。原35B安装错误UNKNOWN不受本实验解释。完整五块M128 Chisel/最终RTL仍各0/5，无新增MAC利用率实测。

## 2026-10-30：Qwen3.5 四块 fresh-host 一次性启动接线（TEMP，未 activation）

- done / PASS（仅源码/轻测）：以已发布 4e2407d5ee830de261511c1f6ad0e8a5b0075b05 为基线，新一次性路径和 nonce 为 qwen35_four_m128_freshhost_20261030_once；schema/profile 明确 registered5、eligible4、P0 deferred、fresh-host。既有 prepare_and_run 入口显式传入 QWEN35_FOUR_P0_BLOCKED_ORIGINAL_HOST_POLICY 及 --fresh-host-profile；仅三项 source pin 更新，其余不变。
- done / PASS（仅 fixture）：9 项 normal/-O 测试分别通过，覆盖新路径/nonce、两份已消耗 activation 保留及拒绝、旧全五块 schema/profile 拒绝、flags/scope 绑定、实际 Git 身份、重试/额外文件/错误资源和事件拒绝。未运行 target host 资格、backend、runtime 或 DUT。
- ongoing / TEMP：先发布上述源码并核验 CI，再单独审核仅新增新 activation 文件的提交，以实际新源码 SHA 为唯一 parent/source。当前未创建 activation，不能称四块已启动。新 host 必须通过既有有界 prebuild 契约，尚未 qualified。
- 保持五 profile 登记：P1–P4 是本次执行候选；P0 按原 host policy deferred / NOT_TESTED，不改其数值基线，不计入已通过。共享完整 4096-MAC 硬件定义未改；vector_lanes32 仅声明 tag，不代表物理 32-lane II=1 已验证。
- 原资源上限、21000秒总时限、并发互斥、每块标定时限和仅上传受限摘要保持。所有历史 activation/失败材料保留，不重跑旧 run、不清理、不上传权重/二进制/原始参考。完整五块 Chisel/RTL 数值仍需真实完成；本次接线测试不能替代数值或 MAC 利用率实测。

## 2026-10-30 四块新宿主运行终态与真实 SRAM 观察候选

- 运行 41081287332（job 124150795368，attempt 1；source 0ebe665a，launch edaf391f）的主步骤已失败。JDK、GNU tool inventory、JAR、Verilator、iDMA、Matrix 六个准备阶段均 native 0；fresh-host inventory 为 native 1，原因码 ELF_DEPENDENCY_ROOT_REJECTED，cleanup/EOF 完整。未进入长 backend 编译、runtime 安装、reference 或 DUT。P0 是策略延期、未测试，不能称实测 CPU 缺 AVX512。
- 原安全摘要为 19,228 B，SHA256 c330617708d91025fcdc91eacd037b9510f2442fec28730d0a6880f3c1b991d1；artifact 12989501775 的 ZIP SHA256 为 9f9e7abe53f806ee272e7b9adba60e5100064b11004d1ed4d16a3bdac6996a9d。拒绝路径未导出，不能猜定原现场路径。只读本地 JDK ldd 显示合法 bin/../lib 路径会被现词法门误拒绝。这是已复现的本地代码缺陷，不等于原 CI 具体根因已完整定位；不重试旧任务。
- 本批发布 candidates/p0_resident_observation_20261030 隔离源码包：从真实 sealed SRAM gate/up 读响应输出 valid-only 观察口，统一 689 bit / 预计 27 port，配套最终 V3 driver collector 和实际 consumer_owned 位比较器。无 ready 反馈，不改算术或 DDR。参考 BF16 位扩展后与 actual 原始 FP32 精确比较，不舍入 actual。该包未替换 active fixed155/backend，原规范化、ABI、RTL 哈希门禁保留。
- 实际本地 Scala typer：155 份源码、五文件 override；native 0，用时 55.460118529998 秒，观测 RSS 892080128 B，严格 cleanup/EOF/gzip 完整。receipt SHA256 为 81f6b9f1bf1f8243c874d45a9a2d6054e4ca7828f103cb9243960b5f4af3d4ba。Debian Java 21.0.12.1 不同于 CI Adoptium 21.0.13；-Ystop-after:typer 不覆盖插件后置阶段、字节码编译、elaboration、真实 ABI、RTL 或数值。C++ 完整 shape 合成 collector、mock-port 语法及 Python helper/owned 测试只按各自范围通过。
- 后续需将观察包与新 source overlay、driver/header、owned-helper pin 链、新 ABI 及实际规范化/RTL 身份共同资格化，不能迁移旧 85 port 或旧 canonical PASS。MoE raw scores 观测及其余 required stage 比较仍未补齐。整个设计的物理 Vector32/II=1 未证明。五块完整 Chisel/RTL 各 0/5，无新增利用率实测；原 35B 安装原因仍 UNKNOWN。

## 2026-10-30：修复合法 ELF 相对路径拼写的误拒（TEMP，未激活）

- 原运行 41081287332 的确切拒绝路径仍未导出。对本机可信 Java 的只读 ldd 和两版解析器直接调用，复现了 bin/../lib/libjli.so 被旧词法规则误拒绝；这只证明本地缺陷，不回填原 CI 未观测路径。
- 新解析先核规范化词法入口，再 strict resolve 并核实际普通文件仍在原系统/toolcache 根族内。合法内部 .. 可通过；真实越界、symlink 逃逸、缺失和目录仍拒绝。保留 raw→canonical alias、实际文件 hash、pin 时重核及原 stage 前后核验。没有扩大根族或资源/版本/硬件/数值合同。
- 失败投影增加固定 query_role、rejection_kind 和 bool had_parent_component，拒绝任意字符串/路径及错误类型；旧 receipt 不凭空补 query_role。公开只给受限标量/hash，无原始 ldd、机器路径或库存。
- 新 unique canonical R2 path/nonce 仅是源码接线；schema/profile、eligible P1–P4、P0 原策略延期、两 flags、预算/并发/摘要限制不变。全部已消耗 launch 保留并拒绝重用。source 与之后的单文件 activation 必须分开。
- PASS 范围：119 项合并 metadata/lifecycle/mock/launch 测试在 normal 和 -O 各通过；本机可信路径解析复现通过。没有新 host inventory、backend、runtime、DUT 或数值通过。下一步必须绑定本源码新身份后做一次独立受限运行；不重试旧 run。

