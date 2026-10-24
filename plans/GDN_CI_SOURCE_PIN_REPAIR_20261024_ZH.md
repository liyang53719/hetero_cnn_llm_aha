# GDN CI 源码 pin 清单修复（2026-10-24）

## 原失败与原因

提交 `5f08bc635734459f26b4f92e2d35783036ad7cbe` 的自动 GDN CI
`40098656294` 真实结果为 FAILED，不改写为通过。90 个 suite 中 89 个通过，
共执行 954 个测试方法；唯一失败 suite 为 `test_ci_fixtures`，其中 1 个断言失败、
1 个 YAML 解析错误，其余 6 项通过。payload guard `40098656276` 通过。

原因是本批 CI 接线将两项 postterminal helper 源码 pin 前插进
`CI_FIXTURE_INPUTS`。该常量并非任意源码列表：既有测试要求它恰好包含原三个
fixture 输入，并使用第 0 项定位 workflow YAML。因此新 helper Python 文件被误作
YAML 读取，同时破坏了 exact-three 集合约束。这是 CI 接线回归，不是模型算术失败。

保留的 artifact SHA-256：
`7055b425f24789fbb933745b8ae426337e058653c2461cc5523aa447836837bb`。
90 份 suite 日志 hash 与 257 个源码 pin 均已对照，源码前后未变，无空 suite 或 skip。
75 项便携测试与 1 项预算回归在该 CI 中均通过，但不能借此声称整个 CI 通过。
此前本地 96 项范围没有覆盖既有 fixture 清单契约，遗漏已明确记录。

## 最小修复

- 恢复 `CI_FIXTURE_INPUTS` 的原三项和原顺序，不放宽既有 exact-three 或 workflow 断言。
- 用独立 `POSTTERMINAL_SOURCE_INPUTS` 清单登记已有 strict-cleanup/bounded-run helper，
  继续纳入 `source_files()` 的前后哈希检查，不丢弃新增源码覆盖。
- 增加明确的清单/顺序、helper 覆盖与 postterminal 测试发现回归检查。
- 不改运行时 adapter、模型算术、owner/reset、比较阈值、fixture 构建或 workflow；
  不减少测试、不允许零测试或 skip，不延长原 120 秒 suite watchdog。

## 验证及剩余边界

修复先在独立源码目录复现原失败，再进行有界、mock/stdlib 为主的聚焦测试；
不启动模型或 native 编译。原 8 项 fixture 测试已复现同样的 1 FAIL + 1 ERROR、退出码 1；修复后 9 项 fixture 测试、原样保留的 75 项 postterminal 测试，以及独立 9 项 runner 审计，共 93 项，在普通与 `-O` 两种模式均通过，无跳过。runner 审计覆盖 15 个 mock 结果场景，包括 13 个应拒绝路径，验证零测试、skip/xfail/xpass/deselected、非零退出、timeout 124、空发现及源码漂移都不能通过；仓库内可复现的是前述 84 项；额外 9 项是发布前独立 mock 审计，不计作仓库新增 suite，也不冒充自动 CI。该审计不启动真实模型或 native 构建。
最终使用精确 main `5f08bc6` 源码输入重建验证目录：257 项源码、90 个 suite 与原 CI 清单完全一致，源码 hash 的差异只限本修复两文件。早期旧支撑快照的聚焦日志只保留为初步证据，不替代这次 exact-main 普通/优化验证。
发布后只跟踪该新 SHA 自动触发的相关 CI，不重复手动 dispatch。
原失败提交及其 artifact 保留，不能用后续成功覆盖失败历史。

历史真实集成 cold128 的已分配指标资格不变；便携 adapter 实际执行仍为
`TEMP_NOT_EXECUTED`，组合 cold/carried 仍为 INCOMPLETE，full-block、RTL、Scala
资源映射未获资格。下一 Qwen2 静态门是独立批次，不混入本修复。
