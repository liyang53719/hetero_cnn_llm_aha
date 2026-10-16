# 有界 bank-only 单元验证（PASS_BANK_UNIT_ONLY）

第一批候选提交：67b01b858724753306d2322504005dd568093f72。
提交 `938bbdbe` 已完成一次有界 Scala 编译、Chisel elaboration 和 Verilator
bank-only 单元运行，结论为 `PASS_BANK_UNIT_ONLY`。
`.github/workflows/raw-kv-bank-unit.yml` 已发布；workflow 文件改变时会触发，
也支持手动触发。本次结果不代表真实 Dense/Attention owner 或完整 block 验收。

## 已验证运行证据

- [单元运行 38862898598](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/38862898598)：三个 ScalaTest 用例全部通过。
- [文本证据 artifact 12029772172](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/38862898598/artifacts/12029772172)：ZIP SHA256 `f29c7512ddfe5521c6fbfd2e41be5425b7268ac6eb189cdc4c666589912941c8`；已核对 API、ZIP 和运行日志。
- 使用同一冻结模型刺激：24,640 个周期，覆盖 4096 行写入/读回；刺激 SHA256 `61f0b7e2cab8dcc347d1d90753eee058e55eea62d7fb514a56e64023aa734ba9`。该计数表示验证刺激范围，不是模型任务耗时或 M128 Attention 性能。
- 四种 CHIRRTL 配置（raw=0/1 × tiles=0/1）均保持 32 个 SRAM：16 个 A（depth=1376）、16 个 B（depth=160），width=256，每 bank 一个读端口、一个写端口。
- 组合后 `TransposedDenseBanks.scala` SHA256：`7cfafc779f15a2e89afd50004bae1d0d30dd6851ab2a4f5a778b1b110e5044c5`；`RawKvUnit.scala` SHA256：`7027b39f2e6b1183501122eaf6695a7e8ef8962ee1f24578c3c2a49730d8e755`。
- 编译/elaboration/RTL 阶段实际墙钟时间分别为 14.20/7.25/38.44 秒（上限 120/60/240 秒）；不是硬件周期或性能测量。
- raw 关闭生成 SV SHA256：`e5140dcfd1267ecbca39e2c4941f1489847620de31292e8540a1beab061977ae`。
- raw 开启生成 SV SHA256：`929ee99d5f7ed70600bec5fde70c5058bc2a88e95e59980a13772dcc3302fcc9`。

这里只验证 bank 端口和现有 FFN typed tile smoke；尚未接入真实 owner、
parentDrained 或缓存发布链路，未完成 full-block/EDA 验证。该 bank-only
单元不含 MAC，MAC 利用率和 duty 为 N/A；不据此推导吞吐或加速比。

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
