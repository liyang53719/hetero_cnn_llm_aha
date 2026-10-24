# GDN synthetic CI 原生夹具接入修复

日期：2026-10-24。此记录只证明主机软件 CI 夹具和有界合成测试，不升级完整模型、完整 block 数值、RTL、时序或有效 MAC 验收。

## 已确认故障

[失败运行 40078194508](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/40078194508) 的 workflow 只构建并导出 legacy Vector16。
- `test_range_contract` 需要 `GDN_VECTOR16_R2_LIBRARY`，因此 setup 抛出 `KeyError`。
- `test_backend_native` 缺少 `GDN_VECTOR16_FINITE_MUL_UF_LIBRARY`，运行 0 项并跳过。聚合门禁拒绝这类结果是正确的，没有改成忽略或假通过。

## 本次修复

- [x] 新增显式 CI helper，使用既有 `build_library` 顺序构建 legacy 与 R2 各一次，保持原严格编译参数和默认异常策略。
- [x] 两份原有 source/compiler/argv/library/ABI 回执均验证后才导出三个变量；两个 R2 名称指向同一 ELF 和相邻 JSON 回执。
- [x] 输出目录必须新建，失败构建或无效回执不写入环境；不查缓存，不隐式下载，不把缺夹具变成跳过。
- [x] Workflow 追踪 R2 C++ 与固定 stimuli；聚合前后源哈希覆盖它们及 workflow；保留所有必需测试和非零计数要求。
- [x] 新增 8 项冷控制回归，覆盖编译/回执失败、既有输出保护、导出路径、顺序、workflow、固定输入集合及测试发现。这些 mock 测试不是原生数值资格。

## 本地复核结果及失败保留

- 显式共享夹具构建：2 次 Vector16 编译、1 次既有共享 Matrix recipe 编译；不是整套测试的编译总数。既有部分 suite 仍自行构建私有测试库，g++ 也可能创建工具链子进程，未统计全部编译进程。重跑复用并重新校验共享夹具，保持既有 suite 行为，没有重新贴标签或修改算术源码。
- 最终定向测试：32 项通过，0 跳过，包括 8 项夹具控制、17 项后端准入、4 项 range contract、3 项真实原生后端测试。
- 第一次完整聚合保留为 FAILED：84 suites / 848 tests，12 suites 出错、98 errors、0 断言失败。11 suites 因稀疏本地 checkout 缺少既有 Matrix endpoint 源文件；1 suite 因本地把构建放在树外，未创建既有测试要求的 `work/` 输出目录。不是两项原始 R2 夹具错误，也不把它们算作通过。
- 完成进程清理后，展开独立副本内全部已跟踪源码目录（历史 reports 除外），检查 246 个聚合/Matrix 必需路径，缺失数为 0；校验原生和 Matrix pins/回执，并补齐正常 CI 已会创建的 `work/`。
- 一次完整重跑：84 suites / 848 tests 全部通过，0 失败、0 跳过；241 个聚合源文件前后不变，Vector 原生身份不变；运行后另行验证全部 Matrix pins 和编译回执，监督进程已回收并验证清理完成。
- 本地 Python 3.12.14，NumPy 2.3.5 / PyYAML 6.0.3 / pytest 8.4.2；1 CPU、2 GiB 地址空间、每个定向阶段 60 秒、聚合 900 秒，并保留原每 suite 120 秒看门狗。运行期禁止网络。

完整计数、失败分类、逐 suite 结果/日志指纹和源码指纹见 [限定摘要](GDN_CI_FIXTURE_REPAIR_20261024_SUMMARY.json)。机器绝对路径、原始日志、ELF 和私有输入不发布。

## 后续及验收边界

- [ ] 发布该小批修复后，核对远端精确 commit，再检查 GDN synthetic CI 和相关 source guard 的该 commit 结果。本地通过不冒充远端通过。
- [ ] 如后续 CI 还有真实故障，保留失败证据并逐项诊断，不减少测试、不接受 0 tests/skip。

未运行或未证明：完整模型/checkpoint 对照、权重获取、完整 block 数值验收、Chisel/HardFloat/RTL、生产硬件绑定、面积时序和有效 MAC 利用率。本次小型原生检查不改变这些边界。
