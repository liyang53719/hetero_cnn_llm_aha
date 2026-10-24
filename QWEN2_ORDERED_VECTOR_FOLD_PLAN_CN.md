# QK16 顺序 fold/scale：本批计划与边界

状态：**TEMP / INCOMPLETE，默认关闭**。本批是独立微模型和轻量回归，不是已接入 Chisel 的优化，也不是完整 block 验收。具体算法、资源计账、真实接口缺口和测试范围见 [候选说明](candidates/qwen2_ordered_vector_fold/README_CN.md)。

1. 保持既有源文件、生产入口和重型 CI 门禁不变。微模型持有 live result，按 row 0..15 顺序逐 key 累加，再按原配方 BF16(dot) → FP32 scale Mul → BF16(score)，逐 key 退休；不得改成 tree sum、FMA、容差比较或整 tile 复制。
2. 独立 [轻量 CI](.github/workflows/qwen2-ordered-vector-fold.yml) 只用 Python 3.12 标准库。使用候选真实的 `--source-root .` 接口校验全部源 pins；`-I -B` 和 `-I -B -O` 各必须恰好通过 12 项，零测试、skip、expected failure 均不算通过。每个子进程最多 30 秒，整段 runner 最多 120 秒，子进程结束及最终结果前后均检查 deadline；每个 Python 进程 CPU 上限 20 秒、地址空间 256 MiB，并绑定一个实际可用 CPU。整个 job 上限 5 分钟，检查 checkout 无改动。
3. 旧冻结版本的隔离启动曾在 `candidates/qwen2_ordered_vector_fold/test_model.py` 导入本地 `model` 时出现 `ModuleNotFoundError`。这是旧启动器在 `-I` 下缺少脚本目录的失败，不是算术测试通过。修正只加入已解析候选目录并检查 `model.__file__`；没有把 production source root 加入 import 路径。原失败证据私下保留，公开记录仅移除私有路径前缀，归因不变。
4. 之后须先补齐并审核真实 Chisel 的 16 路 exception flags、acc 初始化、按 key 延迟发布 fault、ACK/债务及 abort/reset 优先级、共享 vector 状态互斥，才能另行讨论默认关闭的集成 patch。此条是后续待办，不属于本批已完成范围；后续工作按用户既有维护授权，另行制定并审核冻结输入、资源预算与验收计划。

本批不运行或触发 manual dispatch、模型权重下载、native-heavy、Scala 编译、RTL/EDA、完整 M128。微模型 step 和主机耗时不等于硬件周期；没有同源完整 block 和固定资源周期分母前，不声称 80%/90% 利用率、whole-block 加速、频率或面积通过。历史 PASS 与历史失败均不改写。

公开证据溯源：`candidates/qwen2_ordered_vector_fold/validation/VALIDATION.json` 保留历史原始字节清单，其中 `candidates/qwen2_ordered_vector_fold/validation/ORIGINAL_ISOLATED_FAILURE.log` 的原始 SHA256 为 `830fdac11347dc862fbce83f5356fc3aad291d2f604d802910d544147fe07a57`。同一相对路径的公开脱敏日志 SHA256 为 `b52bedb4ac9b197adfd6cb06e85cd0b64dc4c7aeadc71bf3e33fc0b0798a9bb6`；唯一变化是删除一处私有绝对路径前缀，保留仓库相对路径、行号、导入语句和错误类型。这是有意且预期的哈希差异；历史 `VALIDATION.json` 不是全部公开文件的发布后字节清单，也不应被改写成这样的清单。

## 2026-10-24：CI 启动失败与窄修复

- 提交 `3c2283a998290c4d59bef25dd894b0dbb2f4d638` 的 [fold CI 40128345899](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/40128345899) 在测试前的 Git 清洁快照失败：Git 2.55.0 在既定 256 MiB 限制下报 `fatal: unable to create threaded lstat: Resource temporarily unavailable`，exit 128，模型测试尚未启动。独立 payload guard 成功不代表 fold CI 成功；旧失败记录保留，不重写为 PASS。
- 本次只在 `git status` 命令加入 `-c core.preloadIndex=false -c index.threads=1`，关闭该命令的并行预加载及多线程索引读取；不写入仓库、用户或系统 Git 配置。源 pins、严格 12+12 测试计数、所有资源/deadline 限制和 dirty/untracked 拒绝逻辑不变。
- 本地 Git 2.52.0 的 18,000 文件普通 fixture 中，旧/新命令均成功。另用共享 31 字节生成文本的 180,000 条目长路径索引，在相同 256 MiB、20 CPU 秒、单 CPU 预算下合成复现旧命令的同一线程错误，新命令成功并正确报告故意缺失的工作树路径为 dirty；这不是原 Git 2.55.0 CI 环境的等同复现。精确 snapshot 的 clean、tracked-dirty、untracked 和恢复 clean 检查通过，Git 配置字节不变；修订后的精确 runner 在独立源 pin 副本上 `-I -B`、`-I -B -O` 各 12 项通过。
- 上述 PASS 仅限本地修复回归，不代表旧 CI 转绿或 Chisel/完整 M128 验收。修复发布后的新自动 CI 必须针对其精确提交另行核验；不手动重跑旧失败作业，也不扩大执行范围。
