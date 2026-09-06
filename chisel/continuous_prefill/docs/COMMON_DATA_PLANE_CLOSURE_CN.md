# 共同数据通路：Qwen2 real16 已接入原 Matrix 和 pinned iDMA

## 本轮完成的范围

以 `cd144f38508358303f2445ee893efb18403a0a99` 的已验证功能 block 为起点，当前数据通路使用一套原 `qwen2_matrix_command_endpoint` / Revision8B-B 16x32 阵列，以及一套原 pinned iDMA backend。Dense 采用16行x32列 tile；QK/PV与Dense共用同一阵列。没有另建16-lane BF16 FMA替代阵列，没有直接修改保留的RTL或生成SV。

原512-MAC + pinned iDMA的真实尺寸16-token单block已在沙箱实际运行通过：H=1536、F=8960、Q heads=12、KV heads=2、head_dim=128，15阶段663,552个FP32输出全部bit-exact。与上一版功能16-FMA DUT保存的15份实际输出逐字比较，也全部一致。权重为确定性合成权重，数值合同仍为固定BF16/FP32有序配方，不是官方checkpoint质量签核。

实际计数：62,408,919 DUT cycles；749,101,056 useful MAC；762,052,608 executed MAC；192,274,432 DDR read bytes；2,654,208成功写回bytes；3,045,760次实际iDMA搬运。最后输出FNV64为 `fe9744aaa5c1c9ad`。MAX_TOKENS=1024只是编译容量，本次请求为16 tokens。

源代码改动已依次进入main：`9c5ac94`是完整Dense tile与共享阵列适配，`7195a5a`是连续数据验证入口，`245efb022a701c7c9a8f5af658a32738b7330473`补齐128-bit记录读取及测试。记录读取器通过真实iDMA读取Command128/descriptor表中的16-byte记录，但尚未实现完整语义译码和图执行。

## 连续性与硬件证据

只初始化权重、输入和RoPE表，中间DDR填毒值；参考计算不服务DUT的读请求。写响应成功后才提交内存并允许下游读取，所有阶段都检查实际输出，包含跨尾行/尾列的独立回归。功能、协议与地址错误必须返回非零并阻止错误结果发布。

生成电路中有一个Matrix endpoint、一个iDMA wrapper、一个ICG，未出现独立HeteroBF16FmaLane。该检查是生成层级核验，不是综合面积/时序报告。编译保留上游PINMISSING、TIMESCALEMOD、width及UNOPTFLAT警告；不能宣称lint clean或800MHz签核。

通过的测试包括：real16完整block；tiny16完整block；H64/F80/T17尾块完整block；48项Chisel单测（包含记录读取器10项，不能重复相加）；145项真实iDMA传输测试；23项记录读取+iDMA集成测试；10项tiny集成故障/恢复/第二请求测试；4项同一真实尺寸DUT的非法启动/故障测试；13项Python验收测试及25项subtests。

## 明确未完成

Host原始Command128图入口、typed descriptor语义译码/作业绑定、完整event调度尚未接入。内部Matrix命令不等于原958-node图/588条命令执行通过，不能新造一个opaque block opcode绕开这一门槛。

`Record128IdmaTop`是独立验证root；后续应将`Record128Reader`接入生产top的共享memory arbiter并复用唯一iDMA，不能在生产top再放第二套iDMA。当前传输为单在途64-byte mailbox、阵列单context正确性调度。Dense满tile可以使用512个乘积，QK/PV仍取16个有效结果；本结果不是吞吐优化或高MAC利用率声明。

官方权重/框架参考、多层生产链、整网q1024、800MHz DC均保持未完成。不得继承其他配置或历史trace报告的性能与时序通过结论。

## 本地agent：只复核与执行

固定到本交付的最终证据提交；保留旧checkout、checkpoint及所有失败日志。依赖是Java17、sbt、Verilator、g++、Python3和锁定iDMA export。交付包内包含`pinned_idma_export.tar.gz`；将其解到新目录并设置IDMA_EXPORT。不需要修改任何Chisel、SV、参考、阈值或脚本。

```bash
git switch main
git pull --ff-only
export IDMA_EXPORT=/absolute/path/to/idma_export
bash chisel/continuous_prefill/scripts/run_pinned_idma_gate.sh /absolute/new/idma_test
bash chisel/continuous_prefill/scripts/run_record128_gate.sh /absolute/new/record_test
bash chisel/continuous_prefill/scripts/run_production_chain_gate.sh real /absolute/new/qwen2_real16 16
```

缺工具/依赖是BLOCKED，不得计为PASS。成功须同时满足gate.exit=0、simulation.exit=0、RESULT状态、15个完整stage、663552输出零bit差异、实际iDMA计数，以及完整二进制/CSV/源码哈希。失败只保留目录并返回命令、版本、首次错误和日志，由开发侧修复，不由执行agent修改代码。

## 下一项开发验收

继续本模型，不扩展模型清单：实现Host Command128读取、typed descriptor的shape/stride/dtype/range权限检查、与当前执行owner的作业绑定，以及共享iDMA仲裁。完成事件必须晚于最后成功写回，错误不能发布依赖。用原有算子命令或明确验证的融合合同表达完整block，不以新的不透明block opcode代替原图。随后在同一真实尺寸real16上复跑当前全部数值/故障门禁，再扩展跨tile、多层和q1024。以上是开发侧工作，不是交给本地agent编码的任务。
