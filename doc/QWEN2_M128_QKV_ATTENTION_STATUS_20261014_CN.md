# Qwen2 M128 QKV 与 Attention 当前状态（2026-10-14）

## 当前结论

本次记录基线为 `217d067b74a66d2046f382faf1b0ebe04f520745`，父提交 `8dd24d4f270484ad5cee0f41375bd4900f8e0ee0`，M16 发布为 `a6d0eb9c4468a26015225757deda857acb56b844`。M16、M128 的真实输入 public21 pc0..8 窄 QKV 软件门已分别完成并独审。M128 Attention 正式 fresh 链尚未执行，完整 block、真实 Host M16/M128 算术 RTL、完整硬件资源与性能均未通过。

下一步先固定代表性 Attention trace，分析真正宽 QK/PV tile 的因果依赖、存储交接和逐 producer 舍入顺序，再推进同次 producer 数值及协议门。不把逐 token 反复调用的低填充方案冒称高利用率 prefill，不通过缩小固定资源分母或放宽门限取得通过。

五个最终目标仍为 Qwen2-1.5B 完整 block、Qwen3.5-0.8B L0/L3、Qwen3.5-35B-A3B L0/L3。阶段预测最低 80%、争取 90%；最终同源完整实际 RTL 数值与固定资源完整周期 MAC 利用率至少 90% 的联合门不变。`U00.2 ongoing`、`U01 to do`、两份 YAML 的 46 个父任务数组及原状态保持不变。

## 已完成：M16 与 M128 窄 QKV 软件门

- M16：a6d0 的六个官方 producer 与三个 typed raw 均逐 bit 一致；远端 cold 20+20 成功。冷 CI 仅检查 source/metadata 合同，不执行远端模型或 RTL。旧 M16 输入恢复与 ab15242 的 TorchVersion 修复证据保持原字节及执行时 source 身份。
- M128 输入：8dd 独立 recipe 使用真实 128 个 embedding 行、位置 0..127；没有重复、插值或 padding 代替真行。fresh runtime preflight、acquire、materialize、capture、audit 五阶段成功，55+55 冷门、每轮 477 元数据拒绝及 22 项实际字节负门已独审。库存为 8 raw / 7,085,056 B，9 inputs / 7,616,512 B，9 reference / 3,670,016 B；只读引用 ignored 数据，不把数据装入本次 source-only 交付。
- M128 actual：首次执行 78.54352224399918 秒，峰值 RSS 608,576 KiB。n0/qr/q/kr/k/v 六个官方 producer 全 688,128 元素逐 bit 相等；qraw/kraw/vraw 三个 typed-recipe 检查也逐 bit 相等。145 个执行源码前后固定，独立审查 104 项全过。
- typed raw 的边界：独立 loop/layout/reduction 与实际 Matrix 源分离，但共享 FP32 FMA/libm 和部分 NumPy FP32 原语；没有官方 pre-bias raw 参考，不能改写成官方 raw 或独立底层 FPU 验收。
- 协议边界：9 个 owner terminal、8 个 public completion 已 retired；pc8 completion 仍 held，V 未 publish，没有 launch result、finalfence 或完整 block terminal，suffix 仍未执行。后端债务归零只适用于这个已封存边界。

M128 原 `SUMMARY.json` 保留执行时 base=a6d0、candidate_commit=null，以及当时 pending-review 字样。后续通过结论来自单独的 `work/qwen2_m128_model_independent_review_20261014/FINAL_REVIEW.json`，不回写旧执行 source。M128 输入独审为 `work/qwen2_m128_input_independent_review_20261014/FINAL_REVIEW.json`。历史 M16 与 55+55 回执不因新发布而改写。

## M128 已观测计数及其边界

- 28 partial、14 drain、98,304 wide Matrix steps
- 402,653,184 次实际 C FMA，与本段 useful MAC 数相等
- 16,384 个 Add16 请求；raw QKV 写 ACK 1,048,576 B
- 软件功能 ticks 1,033,749；读 14,162,304 B；总写 ACK 3,801,088 B
- 45,824 是 burst 写命令与 ACK 的数量，不能乘 64 当作实际字节或解释成 64 B 拍数
- 固定软件 Matrix accumulator 为 5×16×256 FP32，即 81,920 B；这是源码与运行期账本，不是综合资源或硬件端口证明

M16 source useful/executed=12.5% 和本次 M128 QKV useful/executed=100% 都只是工作量比。软件 ticks、进程秒数、读/ACK 字节量均不能提供实际 DDR 延迟、硬件周期或完整 launch-to-terminal 利用率；固定配置 Matrix 4096 与实际 Vector/Scalar 库存必须保留。

## 冷 CI：失败保留，窄修另记

8dd 的原冷 CI `38553697859` 因 GitHub checkout 祖先路径 `/home/runner/work/...` 中的 `work` 被冷审计误认为仓库 payload 目录而失败。原 ZIP 与失败记录保留；不能把本地成功替换成远端通过。

217d 仅窄改 `candidates/qwen2_live_qkv_inputs_m128/tests/test_recipe.py`，将拒绝范围绑定到 checkout 内真实 payload roots。生产 recipe/capture/pins 以及历史 55+55 summary 字节不变。本地 normal/-O 各 57 项、每轮 477 项拒绝、32 个探针各双 mode 通过。217d 原冷 CI `38555039212` / job `115821966812` 已按 exact-head、终态与原工件闭环：input 57+57、model 25+25、两 mode 各 477 元数据拒绝、两个 default 均 `NOT_EXECUTED`。原 ZIP `11890460311` 为 5,842 B，SHA256 `fe2186d2c93692d8060368378a08a9e72604fa730e1ba56bfcd5ef977207f49c`。payload CI `38555039290` 也已 success；这些通过不执行数值或 RTL。

## Attention：有界校准及已冻结官方参考

正式 fresh M128 public 链尚未执行，无 Attention DUT 数值 PASS。已有 3.258411758011789 秒的有界 synthetic profile0 校准，确认每 step 实际执行 512 个 C FMA，不能把单 slice 解释成执行全 4096 FMA。

对原 profile0 M128 方案的预测为 1,585,152 个 Matrix 请求、811,597,824 执行 FMA、25,362,432 useful FMA。活动 slice 内 useful/executed 为 3.125%；另列全固定 4096×step 机会比为 0.390625%。两种口径不能混用，也都不是完整 wall 利用率。硬件资源不因只使用 slice0 而缩成 512。

约 451 秒仅为 synthetic 小规模观测外推的主机模型运行时间粗估（Attention 约 372.193 秒，加历史独立 QKV 78.544 秒），并非 fresh M128 实测或硬件 cycles；数据分布、逐行开销、metadata、memory 和 Python observer 会影响外推。校准回执为 `work/qwen2_live_attention_numeric_m128_20261014/calibration_v1/RESULT.json`。

官方 27 AST 节点参考已完成独审、冻结和 fresh identity 重现：18 个输出节点共 10,027,008 B 均复现冻结 SHA，原 prefix 九节点也保持一致。终审 `work/qwen2_attention_reference_independent_review_20261014/FINAL_REVIEW.json` 的 SHA256 为 `dba8197361bd29ab72cf26e60cfa67f206afc25bd342c3c308714bfb11b39970`；fresh manifest `work/qwen2_live_attention_reference_m128/frozen01/reference/REFERENCE.json` 的 SHA256 为 `f4e58ae7220dee97d3ebe1bf2c995ca5043a76548db2705a9fc90e5d748a6fbc`。参考包尚未发布。原 bootstrap02 的 `BOOTSTRAP_UNACCEPTED_NO_NUMERICAL_VERDICT` 身份保留，不回写为 fresh 回执。这只是 posthoc oracle 准备，不是 DUT 执行、完整官方 forward 或数值通过；不能继承历史软件 PASS。

## 尾部输入与其他未闭环工作

五个原始 BF16 尾部 tensor（wo、gamma1、wg、wu、wd）共 87,297,024 B，以 14 个固定 segment 下载，五个完整 tensor SHA 与 HTTP/range 记录已离线核验。全部保留 ignored，尚未转换或物化模型 roles，也未执行尾部数值；不是完整 checkpoint 下载、完整 checkpoint SHA 验证或旧 full manifest 重建。来源为 `work/qwen2_tail_ranges_20261014/{SUMMARY,tail_manifest,SOURCE_ONLY_FILES}.json`。

live QKV v5 RTL 候选仍为 work-only/default-off；完整 lint 的 signal 9 原因未知。300 秒 / 2 GiB 的独立 XML 尝试在 15.660 秒、采样 2,159,071,232 B 后主动 TERM，返回 -15，无 XML；不据此宣称 OOM。真实 Host M16/M128 算术、完整库存和 global 依赖环仍 blocked。静态 generated SV 的 49 FP32 ALU、17 DivSqrt 与七类 SRAM/queue 仅为局部库存；Vector16 是子池，4096 MAC 源码展开不能替代完整资源验收。

历史前三个完整 typed 软件已分配门保留原状态，与本次窄 QKV/Attention 工作和完整实际 RTL 分列。35B 仍只到 prefix postnorm 及 saved-postnorm router logits；live postnorm 交接、top8/归一化 score/索引 owner、routed/shared MoE、final residual/fence 与 L3 完整链缺口分别保留。

## 本次维护与验证范围

只更新两份中文 YAML 当前状态，新增本说明及只含 path/size/SHA256/status/标量的索引 `reports/execution/QWEN2_M128_QKV_ATTENTION_STATUS_20261014.json`。旧 readiness 文档与索引保持原字节；不改变执行源码、workflow、候选 pins、数值门或任务状态，不运行数值模型/RTL，不 stage/push。

计划字节修改后按现有规则同步 checklist 的 `计划SHA256`。计划/checklist normal/-O 测试及 generated-source 只读 preflight 的原始日志和结果保存在 ignored `work/qwen2_m128_status_plan_sync_20261014/`，索引仅记录元数据。实际复验：计划/checklist normal 与 `-O` 各 91 项通过；独立 plan/checklist validate 两种模式均通过；generated-source 只读 preflight 两种模式均 14/14 PASS。`-O` 保留 pytest 的预期断言警告。仅使用既有 `work/runtime_recovery/site-packages`，没有安装依赖。任何计划/预检通过都不是数值、RTL、全仓 CI 或项目联合验收。
