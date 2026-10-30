# TEMP：4096 MAC 观察接口的 frontend / 单 driver TU 资格

## 状态与证据分层

本包是 source-only，基于 main `d5cc9ff7501c9b99eeb17b03df20006604341bc7`。
没有 launch manifest，不启动重任务。未来另作唯一新文件、直接父提交、首次 attempt 的启动；不重用任何既往 launch 或重跑失败任务。

已完成的前置实测是 IR run `41114764250`：1056 模块顺序不变、恰 8 个已审观察模块改变，9022 annotations；LOW 122 端口中原 85 严格保持，新增 37 个观察输出共 948 bits。新 canonical manifest SHA256 `00897fd49e82036e04195ef6fe2a671e0a3fd948d968de3e47c4dfa7388f6b5c`。既有基线文件不覆盖。CanonicalHighGate 原 baseline 分支 8985 annotations 不变；新增实际候选路径只按本次真实 9022 与精确 circuit/annotation digest 接受。

本包轻测只证明源实现、拒绝路径和摘要投影；合成 Make 正例仅在测试中替换 global Make hash，生产锁不动。另有 2 个变更 Scala helper 加 5 个纯 AST 依赖的真实小编译（14.6374 秒，RSS 272748544 bytes，native 0，严格 cleanup/EOF/gzip）；没有编译 155 源、重新 elaboration、Verilator 或 driver 编译。详见 `OBSERVER_HELPER_COMPILE_20261030.json`，不上传 classes 或日志。

## 唯一允许的实际执行范围

复用原始 155 源、8 个只读观察 overlay、固定 4096 Matrix MAC / 32-lane Vector 候选定义；编译并 emit 原始 HIGH，经已审 canonical 和 annotation digest 变换生成 host SV；随后只执行 frontend scanner、4 个 Verilator native frontend、生成 Make 语法/工具/依赖严格检查，以及 GCC 单个 `host_axi_driver_non_dpi.o` 与真实 `.d`。

禁止 archive、host link、权重、Python reference、DUT 和数值运行。命令显式清空 `VM_HIER_LIBS=`，只指定 `.o` target；产物必须为 ELF ET_REL，真实 GCC depfile 必须包含两组观察 header 的确切 pin。不是 host binary/header 文本推断成功。

新 SV raw/normalized hash 与完整逐模块 fingerprints 是 **OBSERVED_UNREVIEWED**，不能自动重 pin 接受；Verilator 真实 header 必须逐端口对齐实测 LOW 的全部 122 个 name/direction/width。完整 Make 文本和 native dependencies 在执行前受严格 grammar 与固定工具 pin 检查。P0 的 `avx512f` 仅复用既有 exact-token 能力布尔，不代表 runtime/reference PASS，不改变全 5 策略或 CPU 要求。

五块完整 M128 模型数值、同刺激 RTL 数值、有效 MAC 利用率均未由本包证明；新统一硬件的数值通过仍为 0/5，不继承旧 16-lane PASS。更长档、MoE 同分契约仍待既有决策，不在这里修改。

## 时限和资源

`BUDGETS.json` 逐项列明，首 workflow step 记录同一 monotonic 起点，不能在 checkout 或子入口重置：

- 整个 job 保留原 21000 秒（350 分钟）。
- 8 个 prep wall 合计 2640，加每阶段 30 秒 cleanup 共 240，保守 reservation 2880；同时保留原 **1800 秒 prep aggregate 更紧上限**。这不保证所有阶段都能用满各自最大值，动态准入不足即失败，不延长或重试。
- 16 个 inner 阶段 wall 合计 11100，cleanup 480，共 11580；inner 12000 余 420 秒用于受 deadline 检查的 metadata 工作，不是整个 job 12000。
- 3 个 parent metadata 阶段各 300；执行 step 上界 2880+12000+900=15780 秒（263 分钟）。
- first clock、两个 checkout、guard、export、upload 合计 1320；完整声明 envelope 17100，距 21000 余 3900。各原 phase cap、native supervisor 和资源限额不放宽。
- 保留 13 GiB MemAvailable 准入、原 aggregate tree 12081306272 bytes 加 8 GiB 磁盘余量。资源不足不缩硬件。

## 发布边界

唯一白名单 artifact 有两个文件：`frontend-summary.json` 与 `frontend-qualification.json`。前者最多 65536 bytes；后者最多 2031616 bytes；两者总和至多 2 MiB。资格文件递归严格 schema/字段/路径/pin/Make grammar 投影，全部 24 个原始阶段 RESULT 还须 native 0、无错误、严格 cleanup、pipe EOF、gzip finalized。

不上传 HIGH/LOW/SV、annotations 正文、class/object/ELF、原始日志、系统 header inventory、NPZ 或可重建权重。缺回执记观测不可用或 INCOMPLETE，不能推断进程停止或成功。摘要永远 `archive_link_executed=false`、`numerical_pass=false`、`sv_accepted=false`。后续必须人工审新 SV/module fingerprints 与 header/Make/.d，才可推进实际 host build 和数值验证。

## 复核命令（轻测）

```sh
python3 -B -m unittest discover -s candidates/ci_frontend_pipeline_r2_20261029 -p test_observer_frontend_qualification.py
python3 -O -B -m unittest discover -s candidates/ci_frontend_pipeline_r2_20261029 -p test_observer_frontend_qualification.py
python3 -B -m unittest discover -s candidates/observer_frontend_qualification_20261030 -p test_launch_export_budget.py
python3 -O -B -m unittest discover -s candidates/observer_frontend_qualification_20261030 -p test_launch_export_budget.py
```
