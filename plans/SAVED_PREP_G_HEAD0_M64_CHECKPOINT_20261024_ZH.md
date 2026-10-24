# 保存 Prep-g 与真实输入 head0/M64：有界诊断检查点

本项仅在独立检查点整理既有证据与可复现脚本，没有新数值执行、native load、权重加载、原工作树修改或 RTL 执行。原长跑状态仍为 UNKNOWN；本项不是其继续运行。

## done

- PASS，仅配方逐位匹配：2,048 个保存 Prep-g FP32 元素与独立 Fraction 精确有理数 binary32 RNE Add/Mul/Div 配方全部相同。
- 官方 g 对比保持 DIAGNOSTIC_UNASSIGNED：1,587 个字不同，最大绝对差 1.430511474609375e-6，平均绝对差 6.69931829169932e-8；没有已分配 g 验收门槛，不能称为官方 g 数值 PASS。
- PASS，仅节点切片门槛：真实保存 Prep 输入、冷态、head 0、tokens 0–63、8,192 个 BF16 输出，6 个字不同；最大绝对差 9.5367431640625e-7，平均绝对差 1.1937872912426428e-10，满足既有节点门槛 0.03125 / 0.005。不是逐位相等，也不是完整块验收。
- 原策略保持 IEEE fatal-mask 28、R2 finite-mul、P7 split-ln2 chunk exp、legacy ascending FP32 cumsum、row1 streaming、host batch。Prep 本身仍使用 legacy magnitude/floor P7 加 Softplus7，不以 chunk exp 替换其 op4/op7。
- 既有 native 候选执行 13.013652981026098 秒，监督器 14.323243860038929 秒；1 CPU、512 MiB、60 秒计算／75 秒外层预算；自然 exit 0，retained leader 在两轮完整 owned-group 缺席扫描后回收，1,101 项历史 pin 前后稳定。
- 仅保存相对源码与模型／输入摘要、少量聚合指标、CLI 输入的 stdlib/helper 脚本。未包含权重、NPZ、原始 actual/reference/state 数组、完整运行回执或私有绝对路径。

## ongoing

- 已完成父任务／根任务复核并获准本地提交；本执行者不 push，不发布，不触发 CI。
- 复现必须另外提供原始完整源码、匹配运行时、保存输入／参考与私有 provenance；本独立检查点不冒充原数值实现。
- 脚本适配改为 CLI 路径与显式计划摘要，状态为 TEMP_NOT_EXECUTED。仅完成源码语法和静态复核；本轮不重跑数值，历史数值 PASS 不代表适配后 launcher 通过执行验证。
- 清理未确认或结果不确定时，观察状态保持 UNKNOWN／INCOMPLETE，不能仅因此称数值 FAIL；不得自动重试或向无关进程发信号。

## todo

- TEMP：tokens 0–63 后的 state 没有匹配官方 oracle，不能验收。
- TEMP：完整 M128、全部 heads、full-block 数值、RTL、硬件周期、有效 MAC 利用率与 QoR 均未验收。小切片软件墙钟和内存不能替代这些证据。
- 官方 exp／softplus 因子未保存，因子替换只能说明反事实敏感度，不能归因官方运算或证明完整浮点 flags。

详见 `candidates/qwen35_gdn_prefill/saved_diagnostics/README.md`、`pins.json` 与 `observed_metrics.json`。
