# 真实 Matrix 层次 plan-only：采样 RSS 资源 FAIL

**本次实际结论为 `CONFIRMED_ACTUAL_SAMPLED_RSS_RESOURCE_FAIL_NO_PLAN`，不是 PASS。** 原唯一尝试已终态并完成限定原组清理；未得到 plan，后置 checker 未运行。这里发布小复现源、角色 pins 和独审失败摘要，不重跑 native、不提高限额、不改写原 receipt。

## 已观测失败与 CPU 口径

| 项目 | 实际记录 |
|---|---:|
| sampled group RSS 高水位 | **2,148,995,072 bytes** |
| 固定采样限额 / 超额 | 2,147,483,648 / **1,511,424 bytes** |
| outer wall / supervisor elapsed | 21.288634550 / 21.136820402 s |
| sampled group + parent CPU 高水位 | **20.50099467 s（已观测采样值）** |
| receipt final parent + waited-child CPU | **2.045371732 s（不能当总成本）** |
| root exit / normal worker exit / cleanup leader return | 1 / **null** / -9 |
| 最终文件 / bytes / plan 文件 | 20 / 48,395,635 / **0** |

首错是 `ValueError: sampled RSS cap exceeded`。其后“frontend did not exit zero”是 worker exit 仍为 null 时监督追加的错误，**不是 Verilator 自行正常退出 1 的观测**。没有 outer timeout，最大采样间隔约 0.071815 s，未超过 0.1 s 门。

完整最终 CPU **未知**。采样器统计活着的原组与 parent；final 字段只覆盖 parent 加被该 parent wait 回收的子进程。保留的 cleanup 证据出现 backend reparent，可能遗漏未由该 parent 回收的 backend 成本，因此 final 2.045 明显小于已观测 20.501。不能用小值宣称低成本成功；两值的 max 也不是完整进程树 CPU 积分。未来若改命名/覆盖范围，须另审 successor，不补造这次历史、不为补计数重跑。

## 精确尝试与未完成事项

- 原命令为固定官方 Verilator 5.032 Perl frontend：`--cc --hierarchical --make cmake`，selected top `OrderedQkRealMatrixCore`，固定 prefix / assert / 单线程 / no-timing；无 `--build`、gmake、binary、CMake 执行或模型运行。缺 plan 可能回落普通 codegen 的源码风险保留，不能在中断后推断具体 phase。
- 17 个新 staged 输入（48,320,357 bytes）已由 actual 独审单次 fresh hash：common SV、14 provider 源、2 配置。这里仅公开两份小 adapter 源和两配置；48 MB SV、旧 provider bulk、ELF/Perl cache 与数据不上传，也不再次读取大产物。
- 两个新 SV 只是 canonical 22-port 透明 wrapper 与原实现单模块 token 改名；11 明确零输入、12 开放输出的**源码资格**不等于 provider 数值通过。保持原 8×512 源形状，不把一个 hierarchy library 类型当作仅一份状态或八份运行状态已验证。
- 五项 `public_flat_rd` 配置原字节提交，但尚无生成 C++ accessor / 运行读值证明；原配置“八实例/保留状态”等注释仅说明意图，不能升级为本次已验证行为。未包含数值刺激/权重或尚未执行的后继候选。
- 3867 pins / 12 inventories 的 pre/post source-bound pass 保留；独审没有重扫整个依赖闭包。root56 endpoints /31 absence /13 aliases /3 fresh-cwd 门为 expected 向量 + source-bound ck-pass，不是另存逐项 observed hash / syscall / 动态加载轨迹。launcher 自身 hash 在 Popen 前绑定；原工具历史确认 `-I -S -B`、无 `-O`。
- 当前 plan 目录空；无 retained C++/header/ELF 只说明终态现存文件，**不能否认历史瞬态产物或判定停在 parse/width/flatten/hier-block 某阶段**。原 `model_cpp_generated=null` 保留。cleanup 只证明已锚定原组与观察身份的持久屏障、reap、权限释放，不是整机无任务或已回收所有 grandchildren 的声明。

## 48 条警告不替代实际原因

中止前日志有 **48 个 TIMESCALEMOD header**：common SV38、wrapper1、renamed implementation1、tc_clk8；没有观察到 `%Error` header，但这不是完整 lint / warning-free 结果。实际首个中止仍是 RSS 门，不能把 TIMESCALEMOD 倒写为 native 正常退出原因；`--no-timing` 也不证明所有时间单位差异无害。没有自动加 `-Wno-fatal`、取消 verifier 或提高资源门。

旧 4/6 GiB flat full4096 资源 FAIL、DedupGroup/W005、Treadle CPU FAIL 均保留；本次只增加**固定 2 GiB 采样门下的 plan-only FAIL**，不推出所有可能层次路线均不可行。

## 小源码和合成测试的有限 PASS

`source/check_plan.py`、`source/test_plan.py` 与 2 adapter /2配置均为原字节；checker 只核固定官方格式的五个计划文本，不执行 CMake/solver/子工具。官方源码 pins/行范围保留于 `PLAN_CHECKER_SOURCE_BASIS.json`，其中“未知 mangled suffix、尚无 plan”等为源资格历史，不伪造实际输出。

```sh
python -I -S -B candidates/qwen2_core_real_matrix_plan_failure/source/test_plan.py
python -I -S -B -O candidates/qwen2_core_real_matrix_plan_failure/source/test_plan.py
```

两模式各 **54 个小合成检查（51 拒绝）**通过，仅资格化 checker；实际失败未到此 checker。actual 独审是 normal 模式 **642 条检查 +5 小 proof 负控**，不虚称做过额外 `-O` 全产物复读。公开 `EXECUTION_ROLES.json` 是可移植的精确 argv/contract 与 hashes，不是完整私有 runtime、自动执行脚本或新授权。

**阻塞：层次计划尚未获得，provider / 非零 M1 / rawdot-scale-score-attention 数值一次未验，full128 RTL / full29 / 90% 有效 MAC 仍未完成。** 下一步只能先做有界、独审的源码诊断/后继门；本批不自动串跑、不把 canonical 整体任务置 done。
