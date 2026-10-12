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

实际完整 cold16→真实 carried16 另行运行，发布本提交时仍为 PENDING；不以小门替代完整数值门。运行入口为 `python -m candidates.qwen35_gdn_prefill.full_driver`，使用固定 fixture、显式 Matrix/Vector 编译 receipt，并指定 `--rows 16 --projection-policy gdn_pair_k512_independent_fp32_sum --vector-exception-policy ieee_rne_finite_gradual_underflow`。完成32个 terminal 和双 generation 后，用 `full_compare` 对已冻结的官方完整 M16 capture 检查全部已分配节点及双 state；未通过前不启动放大验收。

这次发布仅触发 GDN 软件小门及 Git payload 门，两者预算分别10分钟和原配置。紧凑源、审查和检查记录见[本轮证据](../reports/execution/QWEN35_GDN_PROJECTION_REDUCTION_20261012/)。不提交权重、NPZ、激活或可编码还原的 tensor 数据。

## 清单与资源口径

- done：真实共享资源两段投影 adapter、普通/seeded 同实例切换、排空/poison 小门、冷完整 workflow 和独立源码审查。
- ongoing：实际完整 cold16→carried16 逐节点/state 验真，之后按实测预算推进 cold128→carried128。
- to do：公共 Command128 接入、显式 IEEE 与投影机制的 Chisel 实现、相同冻结刺激 RTL 重放。

两段投影追加 shared Add 和 bank 访问，不能沿用旧完整图周期/流量数当作新实现精确预测。既有 chunk 约2124万 Vector issue 导出的≤3.168%乐观上界仍揭示该保精度映射的结构风险，尚非完整实测周期，更不是已达到80%/90%。Qwen2 cold M128的27已分配官方门维持此前模型通过范围；其他四个典型 block 完整 M128及 S04/Q35B/U00.2/U01 仍 open。
