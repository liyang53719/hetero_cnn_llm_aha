# R2 必修接缝修正

R1 已被独审阻断，不可发布为 GO。R2 只修监测 cleanup SystemExit 与 raw receipt MemoryError 覆盖原 driver 异常的问题，以及对应取消语义。

原 driver 的 Exception、SystemExit、KeyboardInterrupt 身份必须原样传播。纯监测 SystemExit 等非取消故障仅记 sticky FAIL；setup KeyboardInterrupt 明确取消，不启动 driver；cleanup/receipt KeyboardInterrupt 在已有原 driver 错误时不能覆盖原错，没有原错时仍作为取消传播。用户取消不属于“继续算完”承诺。

R1 frozen 原件未改，新源码与父任务合成必须使用 R2 后像。独立 R2 源码复审已通过，外部原件 SHA 为 82dc68d28c9c6feb1c97965d94d1c430f87c2debe5908d0a33682a2ac1de0cf9；范围仍仅源码与合成软件证据，不是 DUT 或 M128 数值资格。

# M128 事件留证片：独立发布计划

## 本片结果

只准备有界、完整原事件留证的软件实现，不执行 DUT、官方参考、native 或 RTL，也不授予 M16/M128 数值 PASS。

新增候选在 candidates/qwen2_ordered_event_stream。所有 Python 源码保持作者冻结字节不变；源码对应 SHA 见 SOURCE_PROVENANCE.json。旧基线、旧 ELF、旧 pins 均未改。所有输出目录、命令和来源描述已使用逻辑仓库路径；没有实际服务 raw events、tensor、模型权重或 native 包。

## 具体变化

1. 九方法原始事件逐条写入有长度和 hash 的本地文件，raw/native ticket 不改写。成功 raw footer 与生命周期验收分开，不再长期保留百万 Python 事件对象或全量 JSON 字符串副本。
2. ticket 碰撞、foreign、重复、乱序、epoch、wrap、abort 等使验收 sticky FAIL，但磁盘可写且在独立容量内时继续保留之后原始 ACK/清债事件。真正 I/O 或容量失败只能留下明确标错的 incomplete prefix，绝不虚构完整。
3. observer 安装/cleanup 失败不改变原服务返回、ACK 或原 driver 异常。严格 source/code 绑定错误仍在执行前拒绝；foreign callback、local/global mask、slot label 保留，不接管。
4. runner 改动只有留证接线，仍保留原 M16 和 1800s 门。与另片 M128/oracle runner 必须经新 composer 合成并绑定联合后像，不能继承任一单片 pins。

## 软件验证与容量

R1 的 95 项×四模式结果未改写。R2 新跑 109 项 -I -S -O 回归/定向测试，另有 14 项 normal 定向测试，全部通过。发布适配只变元数据路径，没有再运行这些测试。

M1/M16/M32 保留 R1 的 stdlib 懒生成合成事件测量及其原 source hash，不冒充 R2 新测量，更不是 DUT 结果。M32 164,547 条记录、15,193,751 字节；writer 递归 Python size 3,489 字节，tracemalloc 写入峰值 14,729 字节，合成进程实测 max RSS 16,640 KiB。递归对象大小不是 RSS，合成 RSS 也不能直接当完整 M128 DUT 预算。

M128 成功事件计数 2,478,339，按候选成功 schema 最大字段宽度计算的文件上界 327,511,498 字节。示例 512 MiB 文件 cap / 成功计数 +64 raw event cap 仍必须独立准入；+64 只是显式有限容限，不保证所有异常尾流都能录完。超过 cap 必须留截断理由和已记录范围 hash。

## 仍需闭合

- 独立 exact review 的终态 receipt 将由发布父任务另行绑定，本交付不预言 GO。
- 与完整 M128 runner/29 节点取值契约/官方参考准备合成新的源码后像及预算，不能只看旧 full-block 491 MB RSS。
- 原完整参考和新完整 DUT 都没有启动；本片不授权执行。
- 固定 4096 MAC，legacy PV 63.57% 上界和 80/90% 阈值不变，当前只做数值准备。

## 可复现方式

R2 在仓库根目录下，对 candidates/qwen2_ordered_event_stream 中五个 test_*.py 脚本运行 python -I -S -O -B；另对 test_resource_faults.py 运行 python -B。R1 的四模式为历史软件结果，不冒充 R2 全四模式重跑。精确命令和结果在 software_tests/RESULTS.json。

容量测量入口 measure_capacity.py，仅允许 --rows 1、16、32，内部设置 AS384 MiB、CPU45s、文件64 MiB、FD64；外层需 timeout 60s。元数据和静态 schema 上界在 synthetic_evidence/。
