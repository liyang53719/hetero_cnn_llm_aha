# U00.2：Attention 完整双 M1 数值与 MAC 实测

精确生产源码 `98c7d80f65c5f05b55726c5239a6e9ec15d1b53f` 的原运行
`38015586840`，pass job `114118686395` 于 2026-10-10 04:42:15 UTC 成功。
已下载工件 `11659653260`，验证 GitHub ZIP 摘要、660 个源文件与精确 Git
对象，并核对 42 个实际存储 terminal 的 canonical/current-append 哈希。
[证据摘要](../reports/execution/U00_2_HOST_ATTENTION_BLOCK_CI_98C7_20261010/summary.json)
记录所有原始身份。本次完成的是 frozen-recipe 完整 block；native 完整验收仍开放。

每个 launch 从 raw hidden 经过 input RMSNorm、Q/gate/K/V、C1 QK Norm、
B1 RoPE、真实 KV append、矩形 GQA、sigmoid gate、O projection、残差、
post RMSNorm、FFN/down、末残差和最终 fence。两个 launch 在同一 DUT 中
连续运行，各 22 命令、296 记录、19 owner、68,608 字节成功写 ACK。
第二个 token 读取第一轮实际已 ACK 的 KV；没有 reset 或参考中间值注入。
原始输入来自官方 cold_m128 行 0/1；这里的 carried1 是位置 1，不能称位置
128 的 carried_m128，更不能称全 M128 或模型 35B 已通过。

## 真实完整周期 MAC

固定资源分母是 `8 × 16 × 32 = 4096 MAC/cycle`，包含 DDR、Scalar、控制及
空闲等待。周期从 launch 接受至首次 terminal，包括接受边沿，排除 constructor、
reset 和故意延迟读取 terminal 的七拍；连续 launch 的累计端口按 delta 取值。
命令窗口加最后 terminal 一拍，与每轮总周期和 MAC 端口计数完全闭合。

| launch | 完整周期 | useful MAC | executed 端口计数 | useful/(4096×周期) |
|---|---:|---:|---:|---:|
| cold0 | 3,106,174 | 18,354,176 | 294,682,624 | 0.1442611% |
| carried1 | 3,109,624 | 18,358,272 | 294,715,392 | 0.1441332% |
| 合计 | 6,215,798 | 36,712,448 | 589,398,016 | 0.1441971% |

这确实说明当前 M1 数据流的 Matrix 利用率很低。Dense 投影和 FFN 命令窗口
占各轮约 85.0%/84.9%，SiLU×up 约 7.32%/7.31%，sigmoid gate 约 3.99%。
这些窗口含 Host 描述符、DDR 和背压，不能命名为纯算术或纯内存瓶颈。
useful/executed 约 6.23%，还叠加大量非发射周期。未保留 Scalar opcode 内部
周期或互斥 stall 分类；现有 stall 事件可重叠，不允许相加充当完整周期拆分。

以上是完整成功 M1 pair 的 RTL 端口实测。GDN 的 0.09381854% 仍仅为固定
源码的乐观架构上界；两者不是同层、同算法或同证据类型。故障样本不作为
成功 whole-block 利用率。当前优先收敛数值合同，不以此启动硬件微优化。

## native 失败的实际含义

原 baseline 7 / AVX2 9 项失败来自官方 Torch BF16 与独立 NumPy 的 M128
producer 审计，并非本次 RTL 最终输出发生 7/9 项失败。那些软件审计的最终
block 输出本身在仓库限内；失败集中在 QK、scale/mask、Q/post-norm 隐藏节点。
[逐节点原值及来源](../reports/execution/U00_2_HOST_ATTENTION_BLOCK_CI_98C7_20261010/native_gap_audit.json)
保留所有失败，不删除、不改阈值。这些阈值是仓库冻结合同，不是上游公开的容差。

实际 RTL 存储输出与 canonical 相同，因此原 canonical 对官方行 0/1 的诊断
可传递到这些相同 terminal：末输出 max/mean 分别为
`0.0009765625 / 0.0000157803` 与 `0.00390625 / 0.000112627`，在
block `0.05 / 0.01` 限内。不过 carried1 canonical QK producer33 的诊断
为 max `0.5`、mean `0.03125`，超过隐藏节点 `0.03125 / 0.005`。
当前没有该内部 RTL QK 值的单独捕获，也未给 GQA native stage 授予验收。

官方 M128 行切片与两次官方 M1 调用可能使用不同 backend 算术；行 1 的
官方 cache 也不是本次 DUT 真实先前写回的 cache。现有结果尚未包含严格同两
token 原始输入、同实际 prior KV 的官方 M1 比较。不能用终端诊断在限内或
canonical bit-exact 替代全部隐藏节点及 native 完整合同。

## 汇总修正和待完成数据

旧 compact 汇总把 carried 参考的 2,048 字节完整 cache prefix 当作实际
1,024 字节新 tail 比较。这是汇总合同错误，原 driver 已在每个命令和最终
状态检查完整物理 DDR，Python 审计也核对完整快照。修正版分别核验完整
prefix 尺寸/来源、当前 tail 与 rope_k/V 对应关系以及认证的 DDR/snapshot
证据。compact 只有哈希，不能独立重新读取 old-prefix 字节；该限制显式保留。
修正版只读汇总复用原 pass/fault 工件，不重新执行两条数值路线。

截至本记录，fault `114118685810` 和修正汇总仍待终态。新增 5 分钟 scope
仅在精确白名单的只读 checker/测试/文档变化、且原生产 job 正文逐字不变时
跳过重复 EDA；未知 diff、缺 base、RTL/driver/oracle 或 job 正文变化均全跑。
原四个数值/汇总 job 的 570 runner-min 上界不变，新 scope 是额外 5 分钟上界，
独立恢复汇总最多 15 分钟；均不是实测成本。未重跑的新 SHA 只引用原 98c7
的实际证据，不声称新 SHA 重新执行了数值。

原运行仅保留哈希，不能事后恢复这两 token 的实际小 tensor。后续采集须在
同次成功运行中保全最小 raw hidden、实际 output、实际 prior KV 及必要隐藏
边界，带逐文件大小、SHA、来源和不含个人数据的清单，仅进受控 CI 工件，
不进 Git，不含可下载权重。两 token 的 raw hidden 4,096 B、trig 256 B、
42 个 terminal 合计 137,216 B、显式 prior KV 2,048 B、最终 KV 4,096 B、
五个内部 GQA 边界的 FP32 容器 480 B，共 148,192 B，加受限元数据；
这只是后续采集预算，不是已经保存或重新验真的证据。休眠的 reference-only 入口准备显式同 prior-state
条件参考和完全官方两 M1 轨迹；缺失原数据就保持不可复验，不用新 fresh
输入冒充原 pass。全 M128、reset/restore、35B、PPA、MAC 目标仍未完成。

U00.2 保持 ongoing，U01 保持 to do，C02.2 保持 OPEN；C03.2/C04.2/C05、
S01/Q35A 与完整模型大项不因本次 M1 子门关闭。
