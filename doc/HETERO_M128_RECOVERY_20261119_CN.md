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
