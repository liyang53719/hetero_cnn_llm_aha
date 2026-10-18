# Host93 获取外层门：独立 SOURCE 候选

当前仅完成源码检查与13项普通/优化模式 mock 冷测。没有实际创建子进程、信号、资源限制、网络下载或包执行；这些冷测不证明真实计时或资源限制已执行。

## 固定复用与最窄修改

从已发布 `development_snapshots/canonical_runtime_ram_source_20261018/run_behavior.py` 同一已验字节选择 `require/save/group_state/observe_exit/bounded` 五函数。原文件SHA256为 `2eda970f0841b8aebffad451c44a414ed5effe6fbb51a3c04900eeec881b65d2`。不加载其完整模块或 native 测试入口，不使用旧工作目录资产。

投影保留 WNOWAIT、未回收leader身份、kill-before-reap、5秒清理与原receipt规则。四个固定单一文本修改均可精确反投影：

1. 子进程每文件 FSIZE 从4MiB变为64MiB，否则JAR会被截断。
2. `env=None` 继承默认平台环境，不覆盖proxy/TLS、不读取/打印环境、不设凭据或fallback。
3. 子进程只选其继承允许集合中的一个CPU。
4. 进入原cleanup时撤销工作期alarm，避免正常临近工作截止的清理被工作alarm中断；5秒原清理仍适用。清理返回后按同一最终绝对截止重新arm剩余收据时间，不重启总预算。

namespace中 AS_LIMIT为512MiB。被投影的原函数在子进程设置AS/CPU/FSIZE/core0；不会修改父进程资源限额。如果继承硬限额更低而无法设置提案值，应失败，不绕过限额。

## 待审预算

- jar87：entry共享绝对1200秒，工作截止1190秒，预留原cleanup5秒、收据5秒。CPU1190秒，单CPU。转移总额512MiB，单文件严格小于64MiB；socket最多30秒。
- hardfloat20：entry共享绝对300秒，工作截止290秒，cleanup5秒、收据5秒。CPU290秒，单CPU。固定payload149157字节，转移cap149177字节（每文件多一字节用于拒绝尾随数据）；socket最多30秒。
- child AS512MiB；每文件OS FSIZE64MiB。日志64KiB是原函数清理后的接受门，并非实时硬上限。日志同样受64MiB每文件OS限额约束。

两个组分别调用，各自全新attempt；不并发、不自动重试。此处的预算和执行switch均不授予执行权限。共享时钟从入口开始，包含源预检与冻结；工作alarm与原WNOWAIT supervision约束子进程，原cleanup之后只使用最终截止剩余时间。继承SIGALRM阻塞或已有real timer均在副作用前拒绝，不改变继承策略。不是cgroup整体内存、内核不可中断系统调用或调度时延保证；真实运行仍需检查elapsed、child receipt与cleanup证据。

## 冷测与默认检查

从本目录，使用显式已发布repo与已审获取SOURCE目录：

    python -I -S -B test_gate_cold.py --repo ABSOLUTE_REPO --acquisition-source ABSOLUTE_ACQUISITION_SOURCE
    python -I -S -O -B test_gate_cold.py --repo ABSOLUTE_REPO --acquisition-source ABSOLUTE_ACQUISITION_SOURCE
    python -I -S -B run_acquisition_gate.py --repo ABSOLUTE_REPO --acquisition-source ABSOLUTE_ACQUISITION_SOURCE --group jar87

测试同raw固定SHA载入外层门，且只从固定已发布冷测源投影 `FakeOS` 类。两模式均为纯mock；无SourceFileLoader、项目pyc或实际子进程。

## 将来由父执行的单组入口

仅SOURCE审与资源预算获准后：

    python -I -S -B run_acquisition_gate.py --repo ABSOLUTE_REPO --acquisition-source ABSOLUTE_ACQUISITION_SOURCE --group jar87 --output ABSOLUTE_FRESH_ATTEMPT --execute-reviewed-acquisition

HardFloat用 `--group hardfloat20` 与另一个全新attempt。wrapper只接受这两组；iDMA connector物化、firtool和Verilator不在此门。下载器源码及两份计划先按固定SHA/长度冻结到新attempt，再以现有Python直接脚本入口运行；JAR/Scala下载字节均不加载或执行。

产物和过程receipt只留新attempt，保留已验证部分缓存。证据准备要求单child预期exit0、原组清理确认、获取receipt与固定计划逐条匹配且没有FAILED冲突。父不重新读取全部JAR做第二次hash；逐文件新hash由固定获取器在实际接收时完成。最终RESULT.json和stdout均仅标作 `EVIDENCE_PENDING_OUTER_EXIT0`、`terminal_success=false`。单独残留文件永远不能授予成功。父必须独立保存本wrapper实际退出码0、实际总耗时不超过本组共享预算，并审获取receipt和WNOWAIT清理证据后才能接受不透明字节；任何非0退出、超时或未知退出都不能接受。该接受不增加Host93 CLASS/IR/SV或完整block资格。

## v2 最窄最终收据修正

v1保留。仅将最终记录改为非PASS准备证据，并在save返回后再检查同一个绝对stop；不新增预算，不改下载器、资源、计划或WNOWAIT投影。独审的两条反例按原情形纳入冷测：save提交后时钟推进301（stop300）必须抛错；save提交后投递TimeoutError，磁盘只能剩待外层实际exit0验证的非成功证据。无法把文件replace和时钟原子化，因此明确使用独立外层退出与耗时的消费合同，不以残留收据代替实际运行结果。
