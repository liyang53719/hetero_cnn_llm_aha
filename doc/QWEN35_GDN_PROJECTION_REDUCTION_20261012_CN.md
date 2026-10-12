# 0.8B L0：两段 K512 投影接入完整 typed 模型

本轮把已经独立诊断的两段 K512 归约真正接入同一完整 GDN 软件协调器：QKV、Z 和打包 AB 的每段使用独立 FP32 accumulator、段内相邻 K 的高半先算，随后用调用方原共享 Vector16 Add 合并两个 FP32 partial，最后只舍入一次 BF16。它是可执行的存储/请求/完成协议模型；不是公共 Command128 已接通，也不是 Chisel 或 RTL 的实现验收。

## 实现和生命周期

原完整 Job 的 BF16 A/W/D 地址、跨度和 dtype 保留。FP32 partial 是明确的驻留结果，不能把物理 D 偷换成四字节跨度。复用原 A-bank 中三个 FP32 tile，分别存两段 partial 和共享 Add 结果；M128/N160 占245,760B，包含在已有 bank 内，无新增阵列或 SRAM。每个最终64B写回包含32个 BF16；末 ACK 与 Matrix 结果/owner 退休后才发布。

实际协调器在同一 owner、同一内存、同一 Matrix/Scalar/Vector 上依次切换新 QKV/Z/AB、旧普通 O/Gate/Up、旧 FP32 prefix seed Down。所有 read/result/seed/ACK 类型由精确 owner authority 选择，不接受仿造字段类型。原普通模式和 seeded 模式的错误路径均保持已接受事务的退休义务；held success 尚未握手时遇到当前响应 poison 必须阻止发布。已接受的成功不会事后改写。

Conv history 和 FP32 state 仍是独立 staging。只有全16阶段及最后残差全 ACK、成功 terminal 被接受，才共同发布双 root/generation；失败保留上一双 root。源快照、初始刺激、所有权和最终输出身份在实际运行前冻结。旧顺序模式继续是默认值，新模式必须显式指定。

## 数值依据与仍保留的失败

固定后端是 Torch2.10 CPU、原 BF16 权重、固定模型 revision 和 Transformers source。两段 K512、pair 顺序和 FP32 Add 由显式 profile 冻结，不能根据待比较输出选参数；vendor 生成内核的 K512 静态证据不等于动态调用次序已证明。

独立候选的两个 M16 窗口：Z/A/B 全 BF16 bit exact；QKV分别124/135个极小值位差，最大绝对差7.0529661e-38/4.7019774e-38，原最大/平均绝对门均通过。冷 M16 原 FP32 state 门从1个失败变为0个失败，最大容差比0.00446651。这仍只是独立候选，不能继承成实际完整 owner 通过。旧全 K1024 pair 候选失败、原 state 失败和原合法 UF 拒绝全部保留。

显式 IEEE 模式只允许有限 UF/inexact，FP32 结果和 flags 不变，invalid/div0/overflow 和非有限仍拒绝。ExpNegative 的原 abs≥80 饱和没有改变。现有 Chisel 的 Vector 异常模式选择、新 K-window/BF16 drain 和完整路由尚未接入；软件通过也不能称当前 Chisel 完整实现通过。

## 本轮验真与复现

17项实际小 adapter 测试覆盖 M16 的 N32/160/192、一个有界合成 M128/K128/N32，以及同实例新模式→普通→seeded；覆盖末 ACK/seed ACK 扣住时 abort、反压、同拍 poison、非有限、FP32 partial 超过 BF16 范围但尚可合并、最终 BF16 真溢出。完整协调器32项控制测试保留双状态提交负例；旧普通/seeded27项继续通过。首个溢出负夹具数值不足的失败日志保留，后来改用确实溢出的输入，没有调整阈值。

全新源目录加精确 Git 基线，按 workflow 原顺序执行共享 Matrix 构建、Vector 构建、全部隔离小测试、工件收集：305测试/21进程，89.424秒全部通过。这包括独立审查发现并修正的错误排空/迟到 poison 缺口。没有历史 work 依赖、缺测试跳过、模型下载或 RTL。

实际完整 cold16→真实 carried16 另行运行，8ef1239a 源码发布时仍为 PENDING；不以小门替代完整数值门。运行入口为 `python -m candidates.qwen35_gdn_prefill.full_driver`，使用固定 fixture、显式 Matrix/Vector 编译 receipt，并指定 `--rows 16 --projection-policy gdn_pair_k512_independent_fp32_sum --vector-exception-policy ieee_rne_finite_gradual_underflow`。完成32个 terminal 和双 generation 后，用 `full_compare` 对已冻结的官方完整 M16 capture 检查全部已分配节点及双 state；未通过前不启动放大验收。

这次发布仅触发 GDN 软件小门及 Git payload 门，两者预算分别10分钟和原配置。紧凑源、审查和检查记录见[本轮证据](../reports/execution/QWEN35_GDN_PROJECTION_REDUCTION_20261012/)。不提交权重、NPZ、激活或可编码还原的 tensor 数据。

## 清单与资源口径

- done：真实共享资源两段投影 adapter、普通/seeded 同实例切换、排空/poison 小门、冷完整 workflow 和独立源码审查。
- ongoing：实际完整 cold16→carried16 逐节点/state 验真，之后按实测预算推进 cold128→carried128。
- to do：公共 Command128 接入、显式 IEEE 与投影机制的 Chisel 实现、相同冻结刺激 RTL 重放。

两段投影追加 shared Add 和 bank 访问，不能沿用旧完整图周期/流量数当作新实现精确预测。既有 chunk 约2124万 Vector issue 导出的≤3.168%乐观上界仍揭示该保精度映射的结构风险，尚非完整实测周期，更不是已达到80%/90%。Qwen2 cold M128的27已分配官方门维持此前模型通过范围；其他四个典型 block 完整 M128及 S04/Q35B/U00.2/U01 仍 open。

## 19:20 UTC：完整 cold16→真实 carried16 原门通过

同一完整 typed 实例连续执行两个16-token窗口，32个实际 owner terminal，最后两次残差分别在所有写ACK后共同发布 history/state，generation依次变为1、2。carried确实消费此前成功的实际双root，无中间参考注入。980.667秒到达实际终态，进程退出0，峰RSS274,112KiB；这是宿主运行成本，不是硬件cycle。49个执行源都与8ef1239a逐项一致，38个实际输出文件先封存hash，再由独立进程比较。

所有原已分配完整节点、双FP32 state、终输出及同实际输入Conv/SiLU门均通过。两状态各262,144元素，原1e-4绝对/相对门均0失败，最大绝对差4.842877388e-7与7.152557373e-7；旧失败点[2,79,101]在真实冷状态已逐位等于官方。末输出cold最大/均值误差0.00048828125/3.387220204e-6，carried为0.0009765625/6.089685485e-6，保持原0.05/0.01门。同实际输入Conv及SiLU两窗口均0数值BF16 ULP；±0位差照实记录。QKV仍124/135个极小BF16位差，原绝对门通过。其余节点也不是一概bit exact；完整逐项值在[实际M16记录](../reports/execution/QWEN35_GDN_PROJECTION_REDUCTION_20261012/ACTUAL_M16_ORIGINAL_GATES.json)。Prep单独门仍未分配，不能算新增PASS。

实际摘要SHA256为ebff26a6e44f51ae481b64489c0c08a20b8160fd97742ba9a6ee3cbb1c7046a5；独立比较原件SHA256为a3ecd57a01231f8c4bb5a2f12bb497fa5d23f6964c68a183193001ce9df06060。历史文件名仍含cold128/carried128，真正行数由identity.rows=16限定，不能把文件名当M128验收。旧FAIL保持原结论。

8ef1239a的[模型轻门](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/38295788115)与[payload门](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/38295788106)均成功。20,776B工件SHA817a3ca55cfa7c12d55581d462c78f35b17a33be82fbc40ce82f57c4ce2726b1，305测试/21suite、47实现测试源/4编译源/21日志都核对精确commit。工件仅保存ELF身份receipt，没有ELF字节；不假称跨环境同binary。

M128全形状短预检复用原独立C ELF，8.136秒内两个窗口QKV/Z/A/B的有限值及原max/mean阈值检查通过；它没有执行旧normal-only准入，不能称旧比较器完整通过。Z/A/B逐位一致，QKV仅1043/1068个极小值位差，最大9.4039548e-38。它没有执行真实owner，也没有给actual注入数据。依此及M16分阶段耗时，19:20:44 UTC启动唯一同源完整cold128→carried128实际模型：3600秒计算预算、4000秒外层进程上限，比较单列；预计35–45分钟，尚未完成。TypedMemory为126,374,528B，完整输出29,999,104B；这些是软件分配/文件字节，不是新增片上SRAM。原Chisel/Command128缺口与五block M128总门继续保留。

## 19:52 UTC：有限 BF16 比较域修复，旧拒绝保留

真实cold128完成全16阶段并发布generation1后，旧比较器在QKV的两个合法BF16 subnormal处提前拒绝。它复用了Matrix→Norm→RoPE候选的normal-only输入准入；实际GDN传输、BF16 RNE和固定Torch BF16类型均支持有限subnormal。原拒绝保留，不将它改写为旧门PASS，也不将这些值FTZ。短C预检只覆盖有限值和原max/mean数值阈值，遗漏该旧域限制，已在上述记录纠正。

新增显式finite_bf16_materialized_prefill_v1比较域，直接将整数BF16编码精确解码到binary64，避免经过宿主FP32 subnormal转换。保留±0位差、所有实际哈希与误差，拒绝全部NaN/Inf；原节点max/mean=0.03125/0.005、末输出0.05/0.01、同实际输入Conv/SiLU≤1 BF16 ULP、FP32 state的1e-4绝对/相对门全部未变。旧normal-only helper源码和原失败结论不变。新结果有独立schema/scope及比较器源码身份，不能说旧normal-only接受范围未变。

独立检查穷举65,280个有限BF16编码并复核Torch固定CPU头文件；全部精确往返。旧合法域65,026个编码及随机对照的指标和判定与原比较器一致。真实cold128两个QKV差分别为93×2^-133及188×2^-133，均保留非零误差；全QKV最大9.4039548e-38、均值2.7149574e-41，1043位差。QKV没有1-ULP门，其最大201 ULP只作诊断，不能挪用Conv的门限。微型官方conv探针在FTZ/DAZ关闭时仍将subnormal归零，记录为具体后端算子行为，不推论全部projection都如此。

当前唯一完整cold128→实际carried128原进程继续，49实际执行源保持原身份。比较器修复只用于完成并封存实际输出后的独立后处理；未得到双窗口终态和全部门前，M128保持PENDING。

## 19:57 UTC：完整 cold128→实际 carried128 模型全部已分配数值门通过

唯一原进程在2154.304秒正常退出0，M=128的两个连续窗口共32个owner terminal，各窗口真正处理两个64-token chunk、全部16头。末残差ACK后双state generation1→2；carried从实际cold成功发布的history/FP32 state读取，没有参考状态或中间输出注入。38个实际输出文件与49个执行源完整封存，实际摘要SHA033697cf2b2972884d5848c82353328cee5e9265a5a9a7df3d2ce9147473d661。峰RSS414,600KiB。54,840,934是软件模型tick，不能当硬件cycle或据此计算RTL MAC利用率。

独立后处理在明确的finite-BF16比较域及全部原数值阈值下通过：两个窗口各17个已分配捕获节点、双state和全部已分配operator门，无缺失冒充PASS。完整两份FP32 state各262,144字、超限均0，最大绝对差9.5367432e-7/8.3446503e-7，最大容差比0.00397622/0.00692638。末输出cold max/mean=0.001953125/4.5970643e-6，carried=0.0009765625/4.5747583e-6，均用原0.05/0.01门。

同实际输入Conv/SiLU均0数值BF16 ULP；cold919、carried925个raw位差全部为±0。QKV仍1043/1068个位差及每窗2个合法subnormal，所有原max/mean门通过；不是所有中间张量与官方bit exact。Prep单独门仍未分配，只保留其可观察子边界诊断；不能把整模型结果提升为每个内部节点都独立过门。旧normal-only拒绝、旧UF/state失败继续保存，未重新命名为PASS。

[完整数值记录](../reports/execution/QWEN35_GDN_PROJECTION_REDUCTION_20261012/ACTUAL_M128_FINITE_BF16_GATES.json)SHA1415ecd5514d0c6b645ae0bc3cb45a3431eaa7f454bda0d3a134edda8705e482；[比较域审查](../reports/execution/QWEN35_GDN_PROJECTION_REDUCTION_20261012/FINITE_BF16_DOMAIN_AUDIT.json)保留旧拒绝及官方位级反例。最终比较器轻门313测试/22进程通过、源身份一致。第一轮313测试均通过但期间补schema/docstring导致source guard正确失败，该失败保留；最终冻结后完整重跑轻门通过，没有重跑实际M128。

验收层级仍是完整typed软件模型。公共Command128、对应Chisel的新投影/IEEE控制/完整路由以及RTL冻结刺激重放尚未完成；五block总验收、S04/Q35B/U00.2/U01仍open。Qwen2 cold M128及0.8B L0 cold+carried M128分别已到模型已分配数值门，下一目标是0.8B L3真正M128模型；35B-A3B L0/L3保持未完成。新增shared Add、bank及全部访存仍需加入完整硬件周期账，≤3.168%是原固定资源乐观风险界，绝非实测利用率或达到80%/90%。
