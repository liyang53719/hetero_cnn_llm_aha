# U00.2：同生产 RTL 的单线程与双线程有界诊断

2026-10-10 UTC。数值主线仍为精确提交
`98c7d80f65c5f05b55726c5239a6e9ec15d1b53f` 的
[run 38015586840](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/38015586840)：
一次冻结构建，pass 和 fault 各自完整执行同 DUT 的 cold0→carried1，再汇总。
本诊断只研究 Verilator 仿真吞吐，不改变硬件资源、命令、浮点或精度门限。

## 启动依赖和身份

只有上述 build job 成功、原工件摘要核验完成后才启动。复用其完整生产 ELF、
SystemVerilog 和原 C++ driver；仅增加一次 `--threads 2` 的 Verilator/C++
构建，不重新执行 Scala，也不重建单线程基线。两者的 RTL 必须都是
`e8b6ab6640ef0b932a0fc976b00b64998094d692698b4f8e134ead0911611510`。
双线程 ELF 记录自己的身份，不能套用原 build receipt。

原 build 已于 03:16:53 UTC 成功，build runner 实际耗时 3617.724 秒。
已下载并核验两个 GitHub 工件，严格包中 15 个文件及 manifest 通过，655 个
构建源码路径和 657 个 compact 源码路径均与精确 Git 提交一致。内层包 SHA256
为 `1cfaf045ca58704016bfecff3f079b7fa708d1d7f7043b0fb014b5da61b7bfb1`，
ELF 为 `f0f194342fe9ab70290069441f48b9863c6ed9ab9bcd5f3991c7f60168073263`。
173 个 JAR 均来自原固定 Maven 路径。消费端仍须实际重取并核验工具字节；
本地只审查保全的包和源码，没有执行该 ELF。

生产 checkout 固定在原提交和原工作根路径；诊断脚本另用触发提交的独立
checkout。原 archive SHA、源码、编译 JAR、工具、iDMA、HardFloat 和实际
生成命令逐项复核。保留 `-fno-fast-math`、`-ffp-contract=off`，driver 为
`-O2`，模型 `OPT_FAST=-O2` / `OPT_SLOW=-O0`。不改变 hierarchical 边界，
不启用放宽 DPI 纯度假设的参数，也不把环境线程变量当成 ELF 已并行的证据。

## 从 reset 开始的两组 A/B/B/A

一次 fresh 官方 baseline/AVX2 捕获构建本次合法输入，并保留原 native 失败。
两个 ELF 使用同一个本地 fixture；不存在 checkpoint 或参考中间值注入。
跨 CI 主机此前存在上游 raw hidden 字节变化，本诊断不要求本次输入与历史
输入相等；A/B 四次之间则必须实际输入字节一致。

- 4096 cycles：原 input Norm 前缀，单次 60 秒上限，仅作等价 smoke。
- 65536 cycles：同一完整 DUT 从 reset 执行至包含实际 Matrix 活动的前缀，
  单次 240 秒上限；不能把整段时间称纯 Matrix 时间。

每组严格按照单线程、双线程、双线程、单线程顺序运行。原 Recorder 的完整
有序事件、payload SHA、实际内存摘要和确定性最终状态逐项相等才给前缀等价。
较长窗口还必须看到 pc0 Norm 成功，32 个 64 字节 W beat 均获确认、2048 字节发布，
随后 pc1 的 Matrix `wideSteps` 有合法正增量。该计数来自真实 `matrix.step.fire`。
顶层 useful/executed MAC 在 owner 完成时才累加，因此不以其早期为零误判
Matrix 没工作。未观察到活跃路径或到期的窗口保持 PENDING，不自动加时。

计时采用原 `PhysicalAxi.step` 累积时间，含事件捕获开销，排除事件序列化和
最终内存摘要；不是孤立 eval 计时。分别报告两个窗口和每次测量，不由 Norm
前缀推断全层加速，也不从部分窗口计算完整 block 的有效 MAC 利用率。

## 资源和失败保全

单 job 上限 180 分钟；内部总预算 9000 秒，其中候选构建至多 6300 秒，
保留 180 秒失败收集。以上是上限，不是实测成本。运行前检查实际 affinity、
cgroup 及其祖先 CPU 配额和 cpuset；有效 CPU 不足 2 或身份不可确认，
结果为 NOT_RUN，不能开始候选构建。两 ELF 绑定相同的两个 CPU，并记录
资源用量、节流、build 和各窗口耗时。OS 线程数量本身不证明 eval 并行。

子进程保留在原监督器管理的独立 worker 进程组内，超时、失败和 worker 被 SIGKILL 后都收回
整组后代。原始前缀含输入/输出数据，仅保留在 job 本地；工件只上传两个
compact JSON，包括身份、计数、比较和耗时，没有权重、NPZ 或原始 tensor。

## 已完成与未完成

诊断脚本的 53 项测试在普通 Python 和 `python -O` 下分别通过，独立审查
通过，包含实际 child/grandchild 的 worker-SIGKILL 回收回归。此处的通过
只属于诊断工具，双线程真实构建、前缀等价及速度仍待 CI。

原 79bbe 的 legacy 回归于 02:45:53 UTC 成功：同一 launch 完整 42 命令、
38 owner jobs，1,409,024 个 FP32 值零位差，17,096,970 cycles；工件
11656633733 的 SHA256 为
`3ce0baebc9e1b62c2263fca57fdbb561d5fc9dc469503700f7a8811d6f632f24`。
它是 16 tokens、两层、合成权重的旧 Host 回归，不能替代 Qwen3.5 官方权重
完整 Attention 或 M128 验收。

U00.2 ongoing、U01 to do、C02.2 OPEN。完整 Attention 数值与故障终态、
完整周期 MAC 实测、native 完整精度、cold128/carried128、reset/restore、
35B 和 PPA/90% 仍按各自门禁验收。GDN M1 的 0.09381854% 是既有源码
约束导出的乐观架构上界，不是本诊断实测，也不适用于 Attention 或 M128。
