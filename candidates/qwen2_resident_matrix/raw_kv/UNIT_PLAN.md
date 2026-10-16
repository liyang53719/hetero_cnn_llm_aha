# 有界 bank-only 单元验证方案（尚未运行硬件阶段）

第一批候选提交：67b01b858724753306d2322504005dd568093f72。
新增文件准备了可复现 runner；尚未运行 sbt、Chisel elaboration 或 Verilator。
`.github/workflows/raw-kv-bank-unit.yml` 是待发布的可安装 workflow。
发布到 main 且该 workflow 文件改变时会触发一次；也支持手动触发。
当前仅准备完成，尚未启动该 CI 或硬件阶段。

## 精确范围

只组合原有 `TransposedDenseBanks.scala` 及既有 Down、FFN、rawKV 补丁。
隔离 sbt 项目编译该文件和 `RawKvUnit.scala`，不编译 Matrix、HardFloat、
Dense/Attention owner、Host 或完整 block。

- CHIRRTL：raw 关闭/开启 × FFN 关闭/开启，共四种配置。
- 对每个实际生成的 CHIRRTL 检查 32 个 SRAM、原有 A/B 深度/宽度和每 bank
  一个 read mport/一个 write mport；检查 raw 端口只在开启配置出现。
- Verilator：3 个 ScalaTest 用例。一个实际 SRAM rawKV 流程，两个既有 FFN
  typed tile 的填充/封存/读取/释放 smoke（raw 关闭和开启）。这是兼容性
  smoke，不是完整默认关闭等价证明。
- 同一 `stimuli.py` 在 Python 模型生成并检查 24,640 个逐周期向量，包括
  全部 4096 行写入/读回、NaN/Inf 原始位、延迟/背压、非法 key、提前 ACK、
  clean release+普通端口冲突、abort/reset 和 ACK+abort 同周期。
  Verilator 用例读取同一冻结 SHA 的 TSV，逐周期先对比输出再推进时钟。
  hostile clear 后再次读取 line0，以检查 SRAM 未被偷写。
- 缓存有效位仍属上层。该 bank-only 单元不代表真实 M128 Attention 集成，
  不生成硬件吞吐/性能/利用率结论。

## 工具与边界

复用现有 CI 版本：sbt 1.10.2、Scala 2.13.16、Chisel 6.7.0、
chiseltest 6.0.0、ScalaTest 3.2.19；Ubuntu 官方包 Verilator；Java17。
这是独立小项目，不加载完整 continuous-prefill 项目。
解析出的 jar 与现有 Maven lock 同名部分逐一校验 SHA；chiseltest/ScalaTest
依赖未包含在旧锁中的部分记录版本文件名和解析 SHA，不声称旧锁覆盖它们。

一次运行，workflow 12 分钟硬上限。runner 总预算 600 秒；依赖 120 秒、
编译 120 秒、elaboration 60 秒、bank Verilator 编译+执行 240 秒。
各子进程创建独立进程组，超时或中断先 TERM，5 秒后 KILL；不自动重跑。
固定 24,640 向量和三个用例，不通过放宽超时来追求成功。

只上传小文本 summary、source SHA、dependency SHA、生成 RTL 的 SHA。
不上传 TSV、原始张量、权重、完整日志、仿真波形、RTL 或编译缓存。
失败会记录失败阶段；若已生成 RTL，仍保存其 SHA。无阶段成功标记就不能
称其通过。

## 本地准备检查

    python -m unittest candidates.qwen2_resident_matrix.raw_kv.test_unit_prepare -v
    python -O -m unittest candidates.qwen2_resident_matrix.raw_kv.test_unit_prepare -v

这两个检查只运行模型向量生成及 IR 审计器负例，不运行编译/RTL。
真实 runner 命令为：

    python candidates/qwen2_resident_matrix/raw_kv/run_unit.py --out /tmp/raw-kv-unit

输出目录必须不存在。启动真实 runner 会生成并仿真 bank RTL。
