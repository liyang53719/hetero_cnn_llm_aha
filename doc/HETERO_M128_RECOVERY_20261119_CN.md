# Hetero M128 恢复检查点（2026-11-19）

状态：**INCOMPLETE，五个完整 block 0/5**。此前云端检查点丢失，旧数值不能迁移到新身份。本页只记录源码/输入复现线索及证据范围，不含权重、执行快照或生成 RTL。

## 固定约束

- 一个原始 Chisel Host 定义、接口和物理容量，4096 MAC。Qwen2-1.5B 典型块、Qwen3.5-0.8B L0/L3、Qwen3.5-35B-A3B L0/L3 只换运行配置与权重，使用真实 128-token chunk，不以 M1 循环代替。
- 保留 Qwen2 FP32 存储，普通 RMS 与 GatedNorm 按各自官方算子精度，不给普通 RMS 无依据地加中间 BF16 舍入。PyTorch MoE 路由基线及待确认同分规则不改，不注入官方专家 ID。
- 参考、原始模型与后续 RTL 回放分层。Matrix FMA 与 iDMA 必须走原硬件；验证回调如采用，仅报告断言，不参与计算。

## done（仅限下列证据）

- 新统一候选 Scala 编译退出 0；CIRCT 1.163.0 生成 CHIRRTL，SHA-256 `27327f10f15ce3effb85859c04ab5b074cdbe92d70163a71e9affb94cbb53d25`。同源 HW IR `38c94fc2ae91abdd82eb86c25991a31218889b062faef22bc745f4717d8867dd`，8 Matrix / 8 ICG / 1 iDMA，105 条时钟断言逐模块计数一致。这是 IR 证据，非运行或断言逐条件等价证明。
- iDMA 固定 upstream commit `2e0b0fe53b6f8823319e2428e2e9abc2db149b7d` 的导出已重建。927 个成员校验，真实 Verilator 预处理完成；历史文件集合 928/928 相同（含清单），926 个字节相同，另两个为环境相关证明元数据。不是完整 Host 链接。
- 35B 两块 cold M128 首 RMS 官方 CPU 参考重建：transformers pin `42ca9701`、权重 revision `62704185bd97ad488cfc404e7caea797396b74dc`，固定 Torch 2.10.0+cpu。首 RMS 参考各 262,144 个 BF16 元素，仅用于比较。Qwen2 与 0.8B 两块首 RMS/投影另有独立项目顺序参考。不得预载任何参考中间值。

## ongoing / todo

- **ongoing**：Arc 真实模型必须保留全部断言。验证回调仅检查旧相位谓词，不参与计算；下面记录 IR/原生子链已达范围，无整块通过。
- **todo**：五块均从 reset 开始，先验证首 RMS 写回、真正退休与首投影真实消费，再沿各自原控制链推进完整 block。35B 后续 MoE 未完成。
- **todo**：模型数值通过后，冻结同一份源码、参考、输入和配置，只生成一份最终 RTL，以同刺激回放五块。完整 block 有效 MAC 利用率尚未实测；按固定 4096 和整块周期计，至少 80%、争取 90% 以上。32-lane 逐元素每周期发射仍是候选，不当作已实现；第二档 1024/1224 待定，不阻塞 M128。

## 19:33 检查点（仍 INCOMPLETE）

- **done，LLVM 降级**：保留原 Matrix/iDMA/ICG 实例的仿真边界；43 处单元素数组拼接以等位重写通过 20 组差分。同一 Host LLVM SHA-256 `b95e55374e0718b81586d4727be753b699d2293a0f6776fb8c37e531de636314`，静态核对全部 105 个检查点。223 个原生端口按真实状态布局绑定，不代表整 Host 已链接。
- **FAIL，未拆分的后端**：固定 LLVM x86 指令选择在 120 秒预算耗尽，未到寄存器分配，无机器对象。当前验证保持状态写入、时钟和断言顺序的编译器分块，禁止靠缩小 MAC 或替换算术绕过。
- **done，iDMA 子链**：真实 iDMA 搬运 256 B，4 读/4 写 beat、1 次完成，覆盖 45 周期完成背压；B 退休后逐字节一致。独立传输功能，不是整块数值、LPDDR 性能或有效 MAC 实测。
- **done，有限初始输入/参考**：五份原命令表分别为 21/17/22/13/18 条；初始输入 35 个只读段（6/6/6/9/8），仅覆盖前三块至 PC2、35B 两块至 PC4。输入清单 SHA-256 `0f5200a55824a430bd88c15ac5e571d045667613125c6376c2ba2485aebfbce7`，普通/-O 一致。Qwen2 PC2 用 FP32 Q bias；0.8B PC2 L0 Z/L3 K 保持原 K 顺序与最终 BF16 舍入；35B 官方 PC4 L0 Conv+SiLU / L3 QNorm 仅独立参考。禁止提前装入中间输出或路由结果。
- **todo**：五块完整 128-token prefill 数值 0/5，最终统一 RTL 尚未冻结/回放；有效 MAC 的完整周期分母与 GQA 掩码口径已有单元测试，未得到 DUT 实测。CI 载荷策略通过不代表功能或性能通过。

## 21:33 检查点（PC0 已退休子集 bitwise PASS，整块 INCOMPLETE）

- **done，统一模型后端**：原 LLVM CFG 拆分可逆核对并通过 verifier，保留状态更新和全部 105 个时钟断言。固定 Host.o SHA-256 `2ea9278b08a4a7f7f2b49e4ab6d482c54023049d8b51941fa87fd062cfc11d7a`；相同观测可执行文件 `7a3f160d17daf23a381c03a341868a134b65fca41813a880d83ddbc0234e7f4e` 固定 4096 MAC、8 Matrix/8 ICG/1 iDMA，不按模型重生成。20:33 五档真实 launch/AR/R 已发生，但旧预算下均无 B。
- **done，PC0 仅已退休前缀**：本轮同文件、同 35 段输入映射，五档并发冷启动，各运行 60,000 / 43,632 / 44,823 / 60,000 / 60,000 周期；两小档到墙钟预算，其余到周期预算。五档都有实际 AXI B 退休。Qwen2 比较 7,680 个 FP32（5 行），四个 Qwen3.5 每档比较 1,024 个 BF16，均逐位相同。35B 两档首批 1,024 元素各只半行。五档均未完成 PC0、未到首投影。运行摘要 SHA-256 `a7c7d4b396583e67792f8fdf6437e16127c90d5ca38dd0632c4ae392e62af2a6`；只读比较摘要 SHA-256 `ff2a7763f0d639fd38f362ff6741ea4128c993c5f383d9db4c40b8466bb52a90`。不是最终 RTL 或模型整块数值通过。
- **done，独立参考/未来输入**：前三块 PC4 为 Qwen2 FP32 K 投影、0.8B L0 官方 CPU Conv+SiLU/L3 官方普通 QNorm。35B L0 PC7 为固定官方 gated RMS（FP32 direct gamma，保留两次 BF16 转换），L3 核验并复用配对 K RoPE。普通 RMS 独立按项目顺序预测，35B 两档每档 262,144 元素与固定官方参考逐位一致，仅限本输入。未来 48 段只读映射覆盖 PC4/4/4/7/7，SHA-256 `0fabc0c012a492bea5529b642af2110363503822df6184af4b50454f626adb97`；没有预载中间值。本轮仍用原 35 段。
- **ongoing / todo**：下一步量化 Host 仿真开销，同时记录原 RMS scalar issue/return 与 token 进度；再核 PC0 完整退休和首投影。五个完整 M128 block 仍 0/5，后续 RTL 尚未冻结/回放。整块有效 MAC 利用率未实测，固定 4096 和完整周期分母；80%/90% 目标、32-lane 候选不变。

## 22:33 检查点（仿真诊断 / 独立参考；整块 INCOMPLETE）

- **done，仅 2,048 周期轨迹**：同 Host.o 和相同 4096-MAC 原生实例，五档只加 host 计时；原始 launch、AXI pre/consume 与周期观察逐条一致，轨迹收据 SHA-256 `462b9cd853c2a3e0241e0a1a83f16abea622ecb022404c7f955d0ab9f72037f5`。该窗口尚未到 B，不冒称新数值覆盖。Host eval 约 60–68% 仿真墙时，实际原生 settle/advance 约 24–31%。不同 vCPU 绑定与 profile 混杂，暂不归因模型；这是软件仿真开销，不是硬件瓶颈或 MAC 利用率。
- **FAIL / 保留旧策略**：同一 LLVM 的 `llc -O1` 在 100 CPU 秒预算内未完成，停在 Host eval 的 x86 DAG Select 合并（SimplifySelectOps），无新对象；旧 O0 对象不变。隔离的原 RMS owner、10 个断言保留，工具 layout 的 8 个内部字段在真实 reset 后可读；活跃微测触发原 format publication 断言（site 30），不能外推成全 Host 故障，不猜布局偏移。
- **done，独立参考（不是 DUT）**：前三块 PC5（Qwen2 分开 FP32 K bias，0.8B L0 官方 rawprep / L3 普通 KNorm）；35B L0 PC8 官方 O Linear（M128/K4096/N2048），L3 从已验 K/V 构造原 Host cache 位布局，不冒称执行官方 Cache.update。下一阶段只读映射 53 段，覆盖 PC5/5/5/8/8，SHA-256 `c69a2de36411dfa37602524c1d416439014b5a5ce5737ee75f16de518da62435`。小 L0 的 32B BF16 dt_bias 只显式填充原 AXI 64B 读的未用高半部，无 cache 或中间值预载。
- **ongoing / todo**：先用同一 O0 对象做 CPU 绑定交叉校准并按更长预算推进实际 PC0 完整退休与首投影；观察微测失败独立诊断。沿有效开销分项改仿真，不缩硬件、跳沿或省略真实请求。整块模型 0/5，最终 RTL 未冻结/回放，完整 MAC 利用率未实测，80%/90% 目标不变。

## 23:33 检查点（五路长跑已启动；整块 INCOMPLETE）

- **done，仅仿真断言回调**：隔离 owner 的 site 30 原失败定位为 LLVM `i1` 无 `zeroext`，实际 true 可传 raw 255，与 C++ `bool` 假设不符。旧整顶回调检测整个低字节，可能错放非零偶数 false，但尚未发现旧 Host 的实际漏报。保留此前逐位数值证据，不将其当作断言全覆盖。新回调只取 `raw & 1`，256 个编码、4 个越界用例与 105 位点计数通过；隔离真实首笔 memory read 受理，故意非法仍报 site 30/exit 86，与独立 zeroext 方案状态逐字节一致。没有改变 Host.o、原算术、边沿或物理资源。隔离收据 SHA-256 `c6de906c97f7192f1c85a7cc3517ad9ec01a4affc1457a5cd1810a8595bf1fe4`。
- **ongoing，五块 128 token**：同一原 4096 MAC Host.o SHA-256 `2ea9278b08a4a7f7f2b49e4ab6d482c54023049d8b51941fa87fd062cfc11d7a` 与 17 个真实原生实例。轻量验证 driver 换回调与预算；五档 8 周期冷测仅覆盖 reset/idle，然后五档并发实际 launch.fire 与首 AR/R。启动收据 SHA-256 `bac5068245e8551efa9df854e4664bd53e5995c4e0732c4cd9d85d8a88ab146f`。本轮用既定 53 段只读映射，覆盖 PC5/5/5/8/8，不是全权重。每档最多 600 万周期 / 6 小时墙时 / 5 小时 CPU 软限；按原身份续查，不重启。终止导出 B 退休数据，不是可恢复状态。
- **done，仅独立参考**：Qwen2 PC6 的 32,768 个 K RoPE FP32；0.8B L0 PC6 官方 eager 压缩后段真实 2×64，输出 BF16 chunk 和逻辑 FP32 state，不重复 Q scale 或 L2；0.8B L3 PC6 官方 BF16 Q RoPE，非旋转维逐位不变。生成物 normal/-O 一致；扩展 55 段只读映射，覆盖 PC6/6/6/8/8，6+6 通过映射测试，但该映射没有用于已启动的 53 段运行。35B L0 PC9 官方 BF16 residual，L3 PC9 官方 BF16 QK 和独立 1/16 缩放，止于 mask/softmax/PV 前，没有独立 DUT QK 输出退休。20+20 参考边界测试通过。
- **todo**：监测五路同一任务首 PC0 完整退休、矩阵投影和完整 block；补齐后半段真实只读输入及独立参考。五块整块数值 0/5，未冻结或回放整顶 RTL，未测完整周期有效 MAC；32-lane II1 仍候选，80%/90% 目标不变。保留当前任务及唯一证据，无删除、无上传权重。

## 11-20 00:33 检查点（长跑证据失联；整块 INCOMPLETE）

- **FAIL，仅运行证据链，不等于 DUT 失败**：原五路任务的会话句柄已无法查询，23:59:44 UTC 后无原子心跳，五份 stdout 约 23:59:48 同时截断，stderr 为空且没有退出码、完成收据、已写回数据或可恢复状态。未确定退出原因，不报仍运行或全体已退出。逐条重构实际 AXI B 和 WSTRB，最后观测周期 189952/294272/294336/473472/193600，均在 PC0；只可确认唯一有效写回 98304/18432/18432/30720/12288 B，合计 178176 B。日志没有 WDATA，不能将这批写回比数值。审计 SHA-256 `3415e0b6ce24d8b1e736b261bb06faf9c30fe27e6139bc01d9783dedbebdd780`。保留证据、不重启原批次。
- **done，仅验证器单测**：新增运行中周期性 B 退休数据导出，从真实 AXI/StrictMemory 夹具核对 B 后 post-fall 边界、原任务与数据哈希、原子代际发布。强制中断两种发布窗口、未到 B、篡改及错误边界检查均通过。未接上正式 Host，不能恢复 Chisel/原生内核或 AXI 状态，不解决长跑会话寿命。
- **done，独立参考**：Qwen2 PC7/8 V 投影和分开的 FP32 bias；原 FP32 存储、矩阵入口 BF16 RNE、原增加 K 的 FP32 FMA 累加均保留，8 个完整 K 列点与分离 bias 的精确参考逐位同；PC9 仅 K→V 冷缓存布局，不验证确认/提交。0.8B L0/L3 PC7 原 gated RMS 与 K-RoPE；35B L0/L3 PC10 官方 post RMS 与 cold causal mask + FP32 softmax + BF16 物化，不含 PV 或实际硬件 scratch 退休。没有把参考派生张量预载。
- **done，后续输入**：59 个只读段覆盖 PC9/7/7/10/10，SHA-256 `587bd76dc22e883ed1da62ecedbc60d4bc2cd13e2d00fc5c9149fcec5b6d1153`，双模式结果一致、6+6 映射测试；原 launch 和资源不变。仅新增 Qwen2 V 权重/bias、0.8B L0 gated gamma、35B L0 post gamma；35B L3 独立 mask 不作为输入。未绑定到旧任务，也不是全权重齐备。
- **todo**：验证长时执行方案；接入退休数值证据并比对前缀，再按新证据链启动五档，不缩 4096 或改精度/路由。仍 0/5 完整原模型，不冻结/回放最终 RTL，整块有效 MAC 无实测；32-lane II1 候选和 80%/90% 目标不变。无文件删除，无权重上传。

## 11-20 01:33 检查点（运行中写回证据 PASS；整块 INCOMPLETE）

- **PASS，仅真实 PC0 已写回窗口和观察器**：原固定 4096 MAC Host.o 和同一 17 个真实原生实例，未重编 Host 或生成最终 RTL。接入 B 后 post-fall 周期证据导出，五路同 128 token 并行，实际分别 9600/31100/31100/42100/42100 周期，有界退出 3（预期未完成）。五档冷启动与五个实际 Arc 读回负例通过。首写回和终止代共十个，B/地址/WSTRB 独立核对；最新代 704/2048/2048/2048/2048 B，合计 4272 个 FP32/BF16 比较值，全部逐位一致。重叠的历史协议轨迹逐条一致。收据 SHA-256 `c069ebee6a7340b3de27a09b613937de2e2e0d92b83b1f857049ce4d2e9f856c`。不是整个 PC0 通过，不是可恢复状态；未重复原失联长跑。
- **done，仅独立参考**：Qwen2 PC10/11/12：原 16 lane 逐组 FMA+顺序归约 QK、原 Softmax 指数多项式/限幅/递增分母及 PV 原序；保留原 FP32 存储，按原矩阵 BF16 入口舍入。M128 Softmax 有 3921 个真实有效位置达饱和，12 个整行 830 值对精确参考逐位同。0.8B L0/L3 PC8 官方 O Linear 和原冷 KV 布局（非提交）；35B L3 PC11 官方 BF16 PV。35B L0 PC11 **仅**官方 router：18/128 行第 8 名并列，共 226 个不同选中专家；完整 MoE 未运行，仍不改原 tie 规则、不注入专家 ID。
- **done，未来只读映射**：60 段覆盖 PC12/8/8/10/11，新增仅 0.8B L0 真实 4 MiB O 权重，两种模式各 5 项测试；原 launch 不变。不因 router 局部参考放行 L0 完整 MoE；未用于本轮五路短测，短测使用前一份 59 段映射。SHA-256 `d6765ca6b02612ae30472ec0cbbf0247fe19f28246b050d40866434ccbbff6a8`。
- **ongoing / todo**：命令退出后分离的轻量保活探针只留下初始心跳，未获持续执行资格；已启动前台专用轻量探针供下一小时核对同一身份。长跑仍需跨时可证的云执行或可恢复模拟状态方案。五块整块原模型 0/5，最终统一 RTL 尚未冻结/回放，完整周期有效 MAC 无实测，80%/90% 目标与 32-lane II1 候选不变。未删除文件、未上传权重。

## 11-20 02:33 检查点（Arc 单分区恢复 PASS；整块 INCOMPLETE）

- **FAIL，仅跨时执行资格**：前台保活探针只留下约 120 秒心跳，下一小时原任务句柄不可查、没有终态；分离式探针没有第二次心跳。原因未确认，不保证同一任务可跨时，也未再启失联旧长跑。标准托管 CI 是备选，已核对 [Actions 限制](https://docs.github.com/en/actions/reference/limits)，未派发。
- **PASS，仅真实 Arc 分区恢复**：原 Host.o、固定 4096 MAC，及原 17 个 native 实例。Qwen2 在 cycle12/tick24 已接收首笔 AR 尚未返回 R，保存 1,622,611 B Arc 状态；另一进程重放此前 12 周期后，用新 Arc 分配恢复同一切点，原进程内活跃的 native/AXI/账本保持。R 仍在 tick25 返回，续 116 周期、50 条观察和最终模型状态一致。损坏、布局不符、高时钟和哈希正确但边界错四例均在返回 R 前拒绝。收据 SHA-256 `05388c00ac8e749b68d1f8cce2b018b3d365ea435f767a85c99f4b4224909d9b`。原三个 native 库未构建完整状态保存，不能由端口像或进程内存复制冒充；未从文件恢复外部组件，没有新长跑、完整 PC0 或整块通过。
- **done，独立参考/输入**：Qwen2 PC13/14/15 的 O 投影、独立 FP32 残差、196608 值的精确原序 RMS，normal/-O 相同。0.8B L0/L3 PC9 残差与 pre-mask QK（融合虚拟 scratch）。35B L3 PC12 官方 BF16 sigmoid 后乘 context；PC13 仅准备真 O 权重。未来 63 段只读映射覆盖 PC15/9/9/10/13（输入覆盖，不等于数值）；两种模式各 6 项映射测试，原 launch 不变、无参考中间值预载，SHA-256 `2ac06d4bf7a2287401daa1fef77d5c322e2a9cb35f52428d763ca030be9dd365`。
- **INCOMPLETE，35B L0 PC11**：当前构建在命令译码处拒绝 0x50，早于张量扫描；现有 legacy streaming 安装条件与完整 MoE 路径构建条件互斥，补齐权重仍不能放行。本轮列出全动态只读权重 1,618,087,936 B、扫描/租约到合并的接入依赖。未改 guard 或 tie，未注入任何专家 ID。
- **todo**：完成真实 AXI/稀疏 RAM/账本的跨进程恢复、再资格化可保存的原 native；并准备可复建的独立云运行。整块原模型 0/5，最终统一 RTL 未冻结/回放，整块有效 MAC 未实测；80%/90% 目标和 32-lane II1 候选不变。不删除文件、不上传权重。

## 11-20 03:33 检查点（iDMA / AXI 独立恢复 PASS；五块整块 INCOMPLETE）

- **PASS，仅原 iDMA 分区**：原固定参数、原 RTL 与 Verilator 5.032 上新增独立 `--savable` 构建，不替换原库。真实 1 KiB 拷贝，在 cycle13 R 握手停顿、cycle56 WLAST 后 B 待握手、cycle57 B 后 completion 停顿分别跨进程恢复，150 周期/300 个 pre/post 端口观察与原库一致，1AR/16R/1AW/16W/1B/1completion、1024B 逐字节同，坏流/截断/高相位/覆写拒绝。外部 AXI/内存前缀仍重放；B 待握手不是 B 通道停顿。收据 SHA-256 `a8a35a52c58941678bbd3e2b0d86fca08a89ed0a737404677f3c0a451734e893`。
- **PASS，仅 AXI 服务组件**：同一 StrictMemory/AxiBus/IndependentLedger 的真状态保存，在 normal/NDEBUG 合计 67 项组件验证。跨进程无前缀恢复 held R、pending B、稀疏字节和计数；覆盖重叠 B 改内存但已持有的 R 不变、重复 B、丢失/损坏/重算哈希的非法状态和发布前中断。未与真实 iDMA 拼接、未恢复 Host/LaunchAccounting。最终复测收据 SHA-256 `e8b488e9bcc7ace4e2336990cd5a8364fa563198916157655c2b38b9480410a2`。聚合版接口已写，双端口共用内存的专用快照用例尚未执行，仍为 INCOMPLETE。
- **done，仅独立 M128 参考**：Qwen2 原 LegacyV0 补齐 PC16–20，独立参考候选可到最终 y；FP32 存储不变、BF16 RNE 入口与递增 K。PC16/17/19 共 2,490,368 个值经独立 std::fma 完整逐位复核，PC18/20 抽样过精确有理数检查，Python normal/-O 一致。0.8B L0/L3 PC10 各 131072 值，真 post gamma 与各自 pin 的 mask/FP32 softmax→BF16。35B L3 PC13/14 的原 O 投影/残差，各 262144 BF16 值；35B L0 PC11 仍只有官方 router，未改 tie、未注入专家 ID、未下载全专家；静态定位还需审核 PC12 的语义表与最终 fence。
- **done，仅只读输入映射**：同一 4096 与 launch 不变，67 段覆盖 PC20/10/10/10/14。只新增 Qwen2 的三份真 FFN 权重及 0.8B L0 post gamma；不预载参考中间值，不接旧任务。六项测试在 normal/-O 各通过。SHA-256 `6a7d45d3258dd06caf9a32e07e32f293a8436c18ebabd1dd47aa9437cf1214c0`。
- **ongoing / todo**：下轮优先将 iDMA、两个 AXI 端口共享的一份稀疏 RAM 和账本、wrapper 调度在同代 checkpoint 做零前缀恢复，然后接原 Arc/Matrix/ICG；并继续 35B 的 MoE 准入及其余参考。完整原模型仍 **0/5**，未冻结或回放最终统一 RTL，80%/90% 不是完整 block MAC 实测。未重启旧长跑、未删除临时文件、未上传权重，未手动发起 CI。

## 11-20 04:33 检查点（真 iDMA 联合续跑 PASS；Matrix 恢复与整块 INCOMPLETE）

- **PASS，仅真实 iDMA + 双 AXI + 共享 RAM + 账本**：原 1 KiB 传输用真实 iDMA，三个原子代从 cycle13 的 held R、cycle56 的待握手 B、cycle57 的 held completion 在独立进程直接续跑，零前缀、零复位、无重发；尾段 274/188/186 条与原库逐条同，1024B 逐字节同，1 B 和 1 completion 各消费一次；四个无效代均在推进仿真前拒绝。之前单 iDMA 需外部前缀，本轮这个运输子系统不再需要。双总线组件另做 normal/-O 各 226 项（含正常/NDEBUG C++），覆盖第二总线坏状态不污染任何 live 缓冲；不是 Host 恢复。联合收据 SHA-256 `c6df072daca4cd4b99edb32ea287c348607eb0d8b505957c506a42e122d452d2`。
- **PASS，仅八个原 ICG**：同 RTL、同功能参数，在三个低相位取独立实例状态，恢复零前缀；150 周期/4800 条低/上沿/高保持/下沿端口及计数观察与旧库同，坏哈希、长度、高相位、覆写拒绝。没有接回 Matrix/Host。收据 `96947ea8dc70f88a026f50a34fd7793d578544aa321608934ef62c1ed4beb9f6`。
- **FAIL，仅 Matrix 直接层次化恢复方案**：同 Verilator 5.032 小型两级实测，顶层 `--savable` 保存并恢复旧进程的 DPI 子对象地址，覆盖本进程句柄；可见顶层寄存器恢复不等于子模型恢复。未解引用旧地址，未重编实际 Matrix；原生成物每个 512-MAC endpoint 有 32 个同类 16-lane 子对象，完整固定 4096 有 256 个。下一步验证子状态分槽保存与 fresh handle 重绑，或保持 RTL 不变的平坦模拟候选。收据 `1215166305ef3afc3dbd07aaf66218de8b5946e3f2c9f3bc2b43ee94d5c42975`。
- **done，仅独立 M128 参考**：Qwen2 保留已达最终 y 的独立参考。0.8B L0 的真 Gate/Up 投影各 458752 BF16，L3 eval dropout/PV 262144 BF16；35B L3 的真 post gamma 和 PC15 ordinary RMS 得 262144 BF16。35B L0 的 PC11/12 做了默认关闭的隔离准入补丁及静态测试，保留先前 retirement proof、真实 scanner 与最终 fence；未编译 Scala、未接 Host、未下载全量专家、未变 tie 或注入 ID，实际原路径仍阻塞。L3 PC16/17 仅诊断。未来只读 map 70 段，覆盖 PC20/12/11/10/15，仅加两份真 FFN 权重和一份 post gamma，不预载参考，双模式各 6 项。SHA-256 `016ec3aceaefff50f20a61ded8cfd067317c6f883cf734387d694761a2542f1e`。
- **ongoing / todo**：本轮不重启旧长跑；下一步处理真实 Matrix 子状态和 Host 的全组件联合恢复，同时在受控构建检查 MoE 准入，继续并行五块。整块原模型仍 **0/5**，统一 RTL 未冻结或回放、无完整 block 有效 MAC 实测；固定 4096 与 80%/90% 目标不变，32-lane II1 仍候选。已核临时清单，未删除或上传数据，未手动发起 CI。

## 11-20 05:33 检查点（两槽桥 / Scala 编译 PASS；真实 Matrix 续跑和整块 INCOMPLETE）

- **PASS，仅同工具生成的两槽小模型**：父 serializer 禁止保存/安装进程地址，按两个真实 scope 分别保留子状态与 sequence。两个切点 cycle7/11 的槽状态、DPI 计数均不同；新进程在 time0 先分配两个 fresh 子对象，再读父子状态与绑定，不做前缀 eval/DPI 更新。尾段 26/18 个 pre/post 记录与不中断的小模型逐条一致，坏清单、错切点、损坏、重算摘要后换槽四例拒绝。Verilator 5.032 不允许在已恢复非零时间后 addModel。收据 `8111b9b2e302874e1ee04a7d19e8e57f0650cde104e881525be8a3788ff4c8f3`。这是机制证据，不是实际 Matrix。
- **done，仅真实 Matrix 布局审计**：从原生成物提取每 endpoint 32 个确切命名槽及各 16 lanes，八个 endpoint 固定 4096。编译器只做绑定语法检查（不链接模型），35 项 normal/-O 各通过。确认子对象共享 endpoint context，保护库的独立 `m_seqnum` 不在子模型 serializer，生成构造未显式初始化它；这是源码风险，不是已观测硬件故障。下一轮按真槽实现同版模型桥，再对 active/held result 做原矩阵轨迹差分。收据 `e37a2565d6d4979ee18d8951f957ef86b40b96e94953f45590c48d77029d0201`。
- **PASS，仅原 LaunchAccounting 观察器组件**：新增状态编解码和 cut/原命令/代身份绑定。真 Qwen2 原21条命令字、夹具事务，normal/NDEBUG 合计46项（24个跨进程零前缀切点、22个拒绝例）；保存 ready/valid 停顿及按原顺序结算，未在真实 Host 恢复。收据 `04fc267eec2b9b2a5b9e60ee3206f2c9ac09d839d1bbf890c4a765fcd90112db`。
- **PASS，仅 Scala/Chisel 插件实际编译**：35B L0 可选 PC11/12 准入候选，原 155 个编译项及 80 份锁定依赖，退出 0，860 classes，117.53s。字节码确认原 emitter 默认关闭、Top 转发同一开关给 Commands。未展开 Chisel、未生成 RTL 或执行 Host；还未观察到真 PC10 退休后 PC11 扫描/批准 lease，未下 L0 缺少的六个张量。PC12 原 fence、tie 与 PyTorch 路由契约不变。收据 `65ee1cb48a718ecfe50de10d3f5e8a679915318c6434ace0c3451f5954d7bb46`。
- **done，仅独立 M128 参考/只读输入**：Qwen2 保留最终 y；0.8B L0 PC13 SiLU、PC14 Down、PC15 第二残差得到 131072 个最终 BF16 参考，不代表 PC16 硬件退役。0.8B L3 PC12 gate、PC13 O；35B L3 保留 PC15，L0 不宣称完整 MoE。未来只读 map 72 段，覆盖 PC20/16/13/10/15；小 L0 PC16 只消耗 DUT 自己产出的状态。仅加两份真权重，未预载任何参考，normal/-O 各6项。SHA-256 `bb254c2081deff8d3f32a84a02e9b235d9e520a682f69c500591635859fe1096`。
- **ongoing / todo**：真 Matrix 跨进程和 Host 全组件同代联合尚未完成；在同一 4096 Top 做受控 MoE 准入，继续并行五块。完整原模型仍 **0/5**，统一 RTL 未冻结/回放，整块有效 MAC 没实测；80/90 目标与 32-lane II1 候选不变。未重启旧长跑、未手动触发 CI、临时清单已盘点无删除、没有上传权重。

## 2026-11-20 06:33 UTC：M128 参考映射与原始模型恢复（整块 INCOMPLETE）

- **done，仅独立参考和输入映射**：0.8B L3 的 PC14 第一残差、PC15 ordinary RMS（FP32、最终一次 BF16）各 131072 值，PC16/17 Gate/Up 各 458752 BF16，使用原真 L3 权重；无 Host/RTL 执行。五档只读输入映射在相同固定 4096 MAC 接口上覆盖至 PC [20,16,17,10,15]，75 段。仅加 L3 真 post gamma/Gate/Up；从未初始化 DUT 产出。normal 与 -O 均 6/6、产物逐字节相同。参考收据 `c8cd0ea997d86dc31990635364b6c6e50ca6042bf0dedb1c0969e045e4350936`，映射 SHA-256 `7815d28e71ca7ef6aedfc3008dd90122f0e9b701389704f180174d9036d2c400`。不是执行 PC 覆盖。
- **done，仅离线审计**：实现并测试 Host 同步截点 admission，逐一要求原始 Arc、实际 Host 单 AXI 与共享 RAM、NativeDispatch、iDMA、固定 8 Matrix/8 ICG、LaunchAccounting 与观测计数；强制同运行/同 launch map/profile、post-fall 及 tick=2×cycle。验过五份组件收据，实际 Arc 和独立 iDMA 在不同拍、不同归属，不可拼接；正例为元数据 fixture。normal 与 -O 均 7/7。收据 `d4db07c9945719f55a6cf7325e673adbe821b09eb0753885478b44ab1b84d9f2`。未对真实 Host 做同拍保存、恢复或数值执行。
- **done，仅 Chisel elaboration 和候选 IR 差分**：同一原始固定 4096 MAC 几何及接口，用默认关闭和私有开关打开各 elaboration 一次。两份 CHIRRTL 各 71852980 字节，差分只有 Commands 私有 gate 的一个常量；不是按模型生成两个硬件和通过结果。收据 `ccc9f81bd0c6d7b3231d09fb092b73513f6a05504c9586408fafe990114c26a3`。实际 IR 静态验证 1049 个定义和 8 个原始 Matrix endpoint；31 个原指令与 88 个 guard/fence 反例检查，L0 PC11/12 只有 opt-in 及假设的正确前序快照下解码，L3 PC16/17 继续拒绝；原 scanner/guard/fence 连线存在。IR 检查 `8d62e80686ad0d66dcd4578c7af80921cdc6425eb287e59ec4ac074f4b1ba175`。只发射 CHIRRTL，未跑 firtool/RTL、未送权重或执行真实指令。
- **done，仅原 512-MAC 单 Matrix endpoint 断点**：原 Verilator 5.032、原 512-MAC endpoint 的 32 个 16-lane 子实例。仅改仿真器生成的序列化桥：省略旧进程句柄、唯一共享 context、子实例按槽保存。原硬件 RTL 未改；生成、archive 和 sibling C ABI 链接通过，原非保存版本保留。两版各 64 拍且 192 条 pre/rise/fall 的全 521 pin 摘要逐行一致；已保存 active c6 与 outReady=0 的 held c10。收据 `0fdc2f09681ea347271a7300d030ea6ec8b091a785d4027117db745542a1b5af`。跨进程分别直接续跑 58/54 拍，174/162 条 521 pin 记录与旧库逐行同，0 前缀 DPI/时钟/reset/命令重发；512 lane 逐位对照、结果/完成各 1，3 个坏输入在任何 eval 前拒绝。收据 `b4fd11ca49d1a521a8781aeeefb36c9804199fb662251c82ab448a3008e06488`。单 endpoint 是分区验证，不是以 512 替代整机；未联跑固定 8 个。
- **done，仅 NativeDispatch wrapper fixture**：加指针无关保存和两阶段 17 句柄归属交接，含全输出镜像、prepared/poisoned/clock 标志。原正常 create/settle/advance 行为不改。双进程 C ABI 替身 44 项，验证恢复后第一次直接 advance 不额外 settle、所有权及错误输入不接管。收据 `682e92d150072e7144f507aea0d3ff27337caab2624f1a72aa79990aa8661565`；未运行真实 Matrix/ICG/iDMA 或 Host。
- **ongoing**：五个真 M128 完整原始模型均 INCOMPLETE（0/5），PC0 全段仍 0/5。没有冻结整块 RTL，也没有同刺激 RTL 回放或完整 block 的实测 MAC 利用率；固定 4096 MAC、80%/争取 90% 不变。没有用 512 替代、缩减序列、注入专家 ID 或改动 MoE 同分。
- **todo**：先做实际 Host 同拍断点与不切分短段逐拍对照，保持五档一起排队；补 0.8B L3 PC18–21，35B L0/L3 用真实前序 retirement、scanner/收尾 fence 和完整权重；仅在五块模型数值通过后冻结重放，第二档待定不挡 M128。临时文件已盘点，无确认可删项，未清理。

## 2026-11-20 07:33 UTC：原始 Host 路径与三份参考终点（整块 INCOMPLETE）

- **done，仅 0.8B L3 独立参考**：真实 128-token PC18 SiLU 与 Up 乘法分开作 BF16 舍入（458752 值），PC19 原无偏 Down 和 PC20 最终残差各 131072 BF16 值。PC21 只审原 typed fence 和 cache/input 归属，未执行或退休。Qwen2 和 0.8B L0 既有独立最终参考不变；35B L0/L3 整块参考未齐。收据 `75f704fda0bd0594394e3a4a0e1f4d06bc4cba743921cf9eaefc078bb30e1d4a`。
- **done，仅初始输入映射**：同一 4096 MAC 接口、128-token 和五档 launch 不改，仅新增真 L3 Down 的 7 MiB 只读段（全 3670016 词逆验）。76 段到 PC [20,16,21,10,15]，PC21 需要 DUT 自产 cache，不预载。normal/-O 各 6/6 且同一哈希 `f10012b8a38907ed1fce2da1768568a62930f5d43fefdd530022ee3d4cb333bc`。覆盖数不代表指令运行。
- **done，仅真实原 Host 42 拍未切分短回归**：原 Host 对象与三个可保存原生组件连接后，Qwen2 短段的 13 条可见原始事件与既有未切分轨迹相同：3 AR、3 R、无 W/B/有效 MAC。实证 c12/t24 在首个 AR 后而 R 前，8 个 Matrix 均 0 gated edge，8 个 ICG 各 12 顶层上升沿。独立比较器 normal/-O 各 9/9，收据 `3c08088044e3ad1faf887edcc097fd20e0abc80143f571769aecce30a4edf198`。这不表示原始 Host 已保存或恢复。
- **done，仅固定 8 Matrix + 8 ICG 组件联合恢复**：复用原硬件模型和已验 sibling，无重新生成。旧版/候选均实际 64 拍，1536 条 521×uint32 输出及边沿签名完全一致；在共同 post-fall c18/t36 截取 2 结果反压、2 计算中、2 等 step、2 完成反压。跨进程零前缀恢复全部 256 子句柄，46 拍 1104 条完全匹配，续跑 4096 值逐位正确，7 个错误快照均在进入轨迹前拒绝。收据 `1ff66f62f7fa973efe61f0c507969bd697c35a9a86ca7ea83b7839df72c5f6ff`；固定 4096 的组件夹具，不是 Host 或 M128，不外推到 0 gated-edge 的实际 Host cut。
- **TEMP / FAIL，仅 Host 联合恢复**：实现真实原 Host 同拍保存与重绑驱动。无切分旧循环与 prepared 循环 127 条 phase-pin 摘要和 13 可见事件一致。c12/t24 真实 Arc/RAM/AXI/Launch/Dispatch/计数和 9 个 ICG/iDMA native 文件进入 staging；新进程只读验出 AR=1、R=0、R 已准备，无 eval。c12 和 c112 的 8 个 Matrix 都是 local 0/0，旧桥同样拒绝，未发布整套快照、未续跑；4 个错误输入拒绝。收据 `64c36705936f48237aca684784c05f5cba02ca1d8a27d4c636b976ebd6b3740a`。独立真实生成模型证明 reset 释放后、局部时钟仍为 0 时 32 子槽序列戳全为正且一致；先验窄化到已 reset 的零沿 cut，不造 clock/reset。诊断 `cef8a1ec5f156399b711a54008f1764c4878b860805e5b01584750b984f97dba`；尚未修桥或证明冷恢复。
- **done，仅 35B 实际 Chisel scanner 组件时钟测试**：用原始扫描器与两个记录读取器、真实 L0/L3 command/descriptor（非 payload），各 216 拍、36 次 metadata 读。7 种场景、1702 次原断言检查，保留 N32 分离和错误拒绝；旧角色格式可被叶子接受，Host 的 N32 约束仍不能跳过。CHIRRTL 降到 Arc 并保留原断言回调；不是完整 Top，也未执行 PC10 retirement、Host 准入或扫描后 MoE。收据 `0b1acb4e73b05746dd97242cb8b27e6bd03f995c67941f42bd2f570b67c533ac`。
- **ongoing**：五块完整原 Chisel M128 数值 0/5，完整 PC0 0/5，仍无冻结的统一整块 RTL、同刺激回放或以 4096×全块周期为分母的实测 MAC 利用率。32 lane II=1 仍候选，80%/争取 90% 目标不变；不改 PyTorch 路由、不注入专家 ID，第二档待定不挡 128。
- **todo**：先限定修复已 reset 但 0 gated-edge 的 checkpoint，再恢复真实 Host c12/t24 并对照未切分短段；随后五块全 PC0/全块并行对照，以及 35B L0/L3 真实 MoE 准入与完整权重链。临时文件已盘点，不删在用或唯一证据，不上传权重。

## 2026-11-20 08:33 UTC：原始 Host 冷截点和完整 PC0 验收（整块 INCOMPLETE）

- **done，仅原始真 Host 整机短段恢复**：仅窄化仿真 Matrix 保存桥，允许已解除复位、无 gated edge 且子槽 stamp 合法的 cut；原三个 archive、4096 资源和硬件源码不变。8 Matrix+8 ICG 的零沿和旧正常沿组件对照通过；仍拒绝复位未释放及破损状态。组件收据 `be193f7fa3a8e92ef1b381124d79a2aaf8708fd5b306a5882867ac227ae60ada`。在原 Host.o 上用同一真 17 native 句柄完成 286 项同拍保存。五档均 c12/t24→c42，新进程首次真实 R 在 t25，不重发 AR；Qwen2 另 c112/t224→c128。六次共 498 条逐拍 pin 摘要、102 条拼接历史事件及边界 Arc 字节吻合，256 个子句柄每次恰好一次释放，6 个负例拒绝。独立重核 1716 个成员 SHA。主收据 `f4b573fd228750f011362af4e849489275f359ab7899a12f3f16b3347462d19a`，第二校验 `3de3346ce0ac830c63f816b2ff523494f0f42bd14013d1379a3c2cc1d4d6c2e5`。短段没有 B、有效 MAC 或 PC0 退役。
- **done，仅真 35B L3 M128 router 独立参考**：校验原 checkpoint 固定范围 1 MiB 后，真实 PC15 输出进上游路由。产出 32768 logits、32768 FP32 probs 和 1024 BF16 top8 分数；8 行 cutoff 同分，未改规则或导出/注入专家 ID，normal/-O 逐字一致。收据 `3d82a2fb0f26da12eb59253c4fdb996e20cf453c79f8bddc52498f1db16a4750`。原 L0/L3 各 9 个 RO view，分别仍缺 1616908288B、196 个范围，必须全 256 专家；权重计划 `850e8825c091844bf7e80c956a8818e5c936708324a19b33d690b62f4fef3572`。没有专家完整数值或 Host 准入。
- **done，仅 PC0 验收器与既有实际短窗口重核**：验收既要根据原始 AR/R/AW/W/B 顺序和 WSTRB 重建已退役字节，又要求完整输出逐位匹配、首条类型化 completion 和 PC=1，不能用匹配窗口代替整段。历史五档共 4272 个值吻合，但全 PC0 仍 0/5；normal/-O 各 7/7，逐字节同收据。收据 `b64dd996d7f5a67740b1232393c0ddf349258d9923a70abed70ea7590a1de377`。仅验收工具和已留存输出，非新增长跑。
- **done，仅 35B L0 opt-in 候选完整 Host 编译/链接和首段 AXI**：精确使用前轮唯一 gate 差分的 4096 Top。直接 arc-opt 在真实第 7 组动态时钟 extern 保守反馈失败；随后在 arc-conv 后按原 17 组边界分区，保持 105 个断言，复用已验 concat/LLVM 控制流合法化，完整 Host.o 生成并按候选新偏移链接。对象 SHA `ade6c674c6ba79d1ff62d5bc798dda8cb7821da37a5c33d45caee1a0868a595f`，链接收据 `c88ca45d1a2fcbea9c69e8bf40e64999bee142adc36a4183a0a4934122f9186f`。实际原输入启动 128 拍，9 AR/9 R、37 条事件与旧版一致，原断言回调 11904 次；无 B、无指令退役、无有效 MAC，预期有界 exit3。短跑收据 `2cda93189549bea8ec442f1ccebd575e48f48f02a1a1fd73df5c88ed4e0af7e1`。不是 RTL，未声称 PC10/PC11 准入或 MoE 数值。
- **ongoing**：固定 4096 MAC 上的五个完整 M128 仍 0/5。Qwen2 与 0.8B L0/L3 独立数值参考已到输出；独立参考、原模型与 RTL 三层分开。未冻结统一 RTL，未做同刺激 RTL 回放，也没有以全块周期×4096 为分母的实测有效利用率。32 lane 每周期发射仍候选；80%/争取90% 不变，未改 MoE 同分或注入专家 ID。
- **todo**：把短段驱动改为有硬资源上限和低频完整观测的分段运行；先跨首个 B（Qwen2 历史 t18635，其他档并行排队）再完成全 PC0，比较真实已退役输出，不继承旧 PASS。35B L0/L3 权重只按 pin 复现，不上传。第二档待定不挡 128。查看过临时清单，不删除有引用、在用或唯一证据。
