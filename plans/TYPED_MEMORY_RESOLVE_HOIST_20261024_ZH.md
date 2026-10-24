# TypedMemory 线性查找整数终点提升：有界独立验证

基线：b74aa569e2576b4b363006acab5529f536e63749。
本项只优化软件物理内存查找，不修改数学、检查时机、owner 握手或 ACK/发布语义。

## done

- PASS：新增 19 个 memory-only 差分测试，0 失败、0 错误、0 跳过。相同 19 个用例分别对基线 Git 对象中的原始方法和优化方法执行，均通过；这是 19 个不同用例的两轮执行，不是 38 个不同用例。
- 生产改动只有 `_resolve`：在原对齐校验后，仅对 exact-int 的 size 将 address + size 提升为一次计算；其他类型走原表达式。保留全量线性扫描、精确匹配个数、返回对象身份和错误消息。
- PASS：AST 对比确认 `_resolve` 之外的生产源码结构不变。没有索引、缓存、字典或 Region 包装器；每次查找仍观察当前可变 allocation map 和区域几何。
- 覆盖：57 区域乱序布局、边界/间隙/连续分配跨界、负值及 56 位上边界、64.0 和 int 子类回退、同数量替换/删除、整图替换、不同键别名/重复对象、目标及其他区域几何变化/恢复、部分重叠语义、错误优先级、多个匹配后继续扫描、失败操作不改变状态。
- 合成传输覆盖：描述符校验、早/短/失败 ACK、重复写、ACK 后未发布的读阻断、显式成功终端发布围栏、publish_many 在覆盖不足或 guard 损坏时的原子性。未运行实际 owner 终端或数值模型。
- 有界微基准：57 区域、141 个不同地址，每种实现每样本 20,000 次，共 5 个交替顺序样本。`_resolve` 中位数 2540.125 → 2155.756 ns/call，减少约 15.13%；`read64` 2951.554 → 2531.735 ns/call，减少约 14.22%。基线与优化读取字节 SHA-256 相同。
- 以上只是本环境合成查找墙钟测量，不是 full chunk、端到端加速、硬件周期或 QoR 结论。
- 差分测试在模块导入后阻断额外动态库加载、子进程、系统命令、进程信号及网络连接，记录为零。未实例化 MatrixService，未运行 native 算术、实际模型或 RTL。
- 证据：`candidates/qwen35_gdn_prefill/typed_memory_lookup_validation_20261024.json` 与 `typed_memory_lookup_benchmark_20261024.json`。微基准可用同目录 `bench_typed_memory_lookup.py` 复现。

## ongoing

- 独立本地小提交供复核；本执行者不 push、不更新远端、不触发 CI。
- 原工作树及 UNKNOWN 长跑保持不触碰，不重放、不发进程信号。本次只从独立仓库 Git 对象补齐三个纯 Python 文件。

## todo

- TEMP：full M128 数值执行未运行、未验证，不能由本项 PASS 推导通过。
- TEMP：RTL 未执行、未验证，无硬件性能验收结论。
- TEMP：依赖已验证原生库的完整 Dense/owner 终端套件未运行；本项仅 memory-only 合成范围。
- 合并或发布由父任务另行协调；本证据不继承其他历史测试或数值 PASS。

## 复核命令

- `PYTHONDONTWRITEBYTECODE=1 python -m unittest -v candidates.qwen35_gdn_prefill.test_typed_memory_lookup`
- `PYTHONDONTWRITEBYTECODE=1 python -m candidates.qwen35_gdn_prefill.bench_typed_memory_lookup --iterations 20000 --samples 5`

生产文件 SHA-256：fac5ab5f56602132691c91074fc15b364b8a1f52aef329eab7b1ceb3060f8529。
