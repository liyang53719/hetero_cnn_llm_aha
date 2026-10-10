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
`-O2`。Make 变量为 `OPT_FAST=-O2` / `OPT_SLOW=-O0`；首轮实际命令核查发现
后置 `-CFLAGS -O2` 覆盖 Slow 配方，302 条普通和 221 条生成 Slow 源码的最后
有效优化参数均为 `-O2`。不能把 Make 变量称为最终有效 `-O0`。不改变 hierarchical 边界，
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
整组后代。原始前缀含输入/输出数据，仅保留在 job 本地。首轮工件只上传两个
compact JSON；因此首轮候选 ELF 只有哈希，无法恢复。修复后的保全方案在
独立工件内只列出候选 ELF、相同 SV、生成 top C++ 和六份既有身份/配方文件，
共九个固定文件；compact 另行保留并回显日志。没有权重、NPZ 或原始 tensor。

## 首轮真实失败和有界修复

诊断提交 `7ea2fd42e3f66c26018e3ad6a5e6a57ba4460319` 的
[run 38020436763](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/38020436763)
于 04:18:05 UTC 失败，工件上传成功。单个 threads2 候选构建成功，耗时
2707.520 秒，SV 字节未变；实际可用 CPU 为 4，A/B 均计划绑定 CPU0/1。
两个 fresh 官方执行也已完成，但在第一次前缀之前遇到诊断脚本错误：
`built/live source closure mismatch`。实际完成前缀为零，没有速度结论。

原因是把 fresh 后 658 项“构建加参考”源码并集传给只含 655 项源码的构建
身份检查。额外三项都是官方参考脚本；655 个共同路径没有哈希漂移，658 项
全部匹配冻结 98c7 Git 对象。修复要求构建检查使用完整不变的构建集合，
额外参考源另行全部对冻结提交核验，并严格检查两集合的完整并集；缺件、
额外项或任意漂移均拒绝。原完整 Attention runner 使用独立 fixture 集合，
不含这一诊断错误；原 pass/fault 作业继续。

首轮只有摘要和哈希工件，无法复用已完成的候选 ELF。后续恢复若获执行，
必须再构建一次候选，成本规划采用此次实际约 45.1 分钟；仍复用原基线，
不自动延长窗口或增加完整数值批次。原失败及身份保留在 `first_attempt.json`，
不得以修复后的源码重新绑定此轮失败或声称已经完成 A/B。

## 已完成与未完成

首版诊断工具的 53 项测试在普通 Python 和 `python -O` 下分别通过，但它们
没有覆盖本次真实构建与参考闭包的差集，不能据此声称原工具完整正确。首轮
首轮真实双线程构建已经完成，但当时没有前缀等价或速度结果。修复后的 78 项测试在普通 Python 和 `python -O` 下均通过，增加真实集合合同
及多余、缺件、漂移负测，并保留 child/grandchild 的 worker-SIGKILL 回收回归。
只读预检还重新核对归档 655 项构建源与各工厂完整集合的 658 项并集，全部匹配
冻结提交及当前字节，不执行模型或 EDA。

原 79bbe 的 legacy 回归于 02:45:53 UTC 成功：同一 launch 完整 42 命令、
38 owner jobs，1,409,024 个 FP32 值零位差，17,096,970 cycles；工件
11656633733 的 SHA256 为
`3ce0baebc9e1b62c2263fca57fdbb561d5fc9dc469503700f7a8811d6f632f24`。
它是 16 tokens、两层、合成权重的旧 Host 回归，不能替代 Qwen3.5 官方权重
完整 Attention 或 M128 验收。

## 修正版实测终态：双线程较慢，不采用

精确诊断源码 `5ff4ca072b5aa707b18fa48730d572f4a2e59a36` 的
[run 38024322165](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/38024322165)
/ job `114131802450` 于 05:44:55 UTC 成功。两个 ABBA 窗口都完成，事件、
terminal、计数及内存摘要严格一致；658 个生产源与冻结 98c7 匹配，诊断
driver 与 5ff4ca0 匹配。候选构建实耗 3,261.16 秒，原单线程 ELF 未重建。
compact 工件 `11661242028` 与候选九文件工件 `11661007086` 均已下载核验
GitHub 摘要；候选 ELF、相同 SV、生成 top C++ 与构建脚本摘要也逐一相符。

| 完整 DUT 的有界前缀 | 单线程 step 均值 | 双线程 step 均值 | 双线程耗时增加 |
|---|---:|---:|---:|
| 4096 拍 Norm | 5.1590 秒 | 6.2838 秒 | 21.80% |
| reset 至 65536 拍 Matrix 活跃窗口 | 84.3779 秒 | 103.8821 秒 | 23.12% |

长窗口在第 17,082 拍完成 Norm 发布及 32 个写 ACK，第 20,532 拍首次
Matrix issue，共真实发射 1,280 次；没有注入 checkpoint 或跳过前序计算。
双线程进程平均占用约两核，单线程约一核。计时含 step 捕获开销，未隔离
eval、纯 Matrix 或完整层，不据此声称完整 block 提速。此候选不采用；原
数值路线继续使用原 ELF。先前身份失败记录和本次负性能结果均保留。

独立的原 Attention pass 已通过完整双 M1 frozen-recipe，并取得协议背压
条件下全周期 MAC 实测；见 [完整数值及统计范围](U00_2_HOST_ATTENTION_BLOCK_CI_98C7_20261010_CN.md)。
原末 ACK 故障协议和只读修正汇总也已通过，详见上述完整范围记录。
U00.2 ongoing、U01 to do、C02.2 OPEN。native 完整精度、cold128/carried128、reset/restore、
35B 和 PPA/90% 仍按各自门禁验收。GDN M1 的 0.09381854% 是既有源码
约束导出的乐观架构上界，不是本诊断实测，也不适用于 Attention 或 M128。
