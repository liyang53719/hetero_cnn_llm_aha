# 同 job 最小实际执行接线候选（仅源码，NO GO）

实际调用链为 flow.py → 原 BUILD_ONLY backend（先完成，失败不下载材料）→ 官方原锁 archive-only → 原 70 tensor acquisition → 三原安装与新 fresh owner → 原五块 M128 Python reference → 同一 binary 五 profile provider/consumer。无 workflow、无 activation、无公开 payload 上传；不是新的参考算法或硬件定义。

新代码分为本目录、fresh_job_runtime_r2_candidate_20261030T0857、same_job_execution_r7_candidate_20261030T0829。所有执行必须由独立审核 binding 固定源码/tool/source/launch 身份。旧本地 owner/安装 receipt 不移植，fresh owner 只认同 job 新产生的三安装原 receipt、sidecar、全树 identity 和 cleanup。原四个 P0 producer 源不改，bootstrap 的差异只追加共享 watched root 与全 job 时钟/预算传递。

完整控制流 mock（1 方法）、reservation/源码测试（5 方法）及资源/顺序测试（4 方法）normal/-O 均通过；mock 替换 acquisition、installer、reference、build、consumer，不包含实际安装/下载/模型/DUT。fresh owner 11 元数据/小树测试与 phase wiring 4 测试另列，非真实执行证据。

## 未准入的最小项
- 独立审 top controller 与 fresh runtime 的实际接口/闭包；源码可审不代表可运行。
- 需要 NEW 唯一 CI source/launch/binding 与第一工作流步骤的 monotonic 起点，目前没有 workflow 或实际运行身份。
- 实际 runner 必须通过原 Python 3.12/x86_64/P0 AVX512、ImageVersion 20261026.354.1、原 JDK gate；滚动 image 不自动继承资格。
- 初始磁盘保守门为 12,081,306,272 + 8 GiB = 20,671,240,864 B free，不能由“标准 runner 14GB”推导通过。没有清理步骤或峰值保证。
- 五个完整 128 刺激全登记，只缩诊断 wall，不改 tokens/max_cycles/4096/数值算法。各阶段有限预算总和须 ≤ 21000 s，例子只是测试输入，未批准实际预算。
- 尚无 DUT cycle/rate/RSS 证据；driver 每 2^20 active cycles 才发 running 进度，短标定可能得不到速率。所有完整数值仍 INCOMPLETE/0 of 5。

阶段属于 Chisel 测试发射 IR/SV 的仿真 backend，不是原生解释器，也不是模型全过后的最终冻结 RTL replay。原 strict supervisor 未改；proc/RSS 采样可能被磁盘 census 阻塞，不能冒连续峰值。无重跑现有五参考、无 EDA、无上传、无删除。

## R2 根/子审四项修复
- backend先行，未恢复大权重时通过原512MiB watched-file门；四个原P0 producer字节不变。build失败停止，fresh材料不启动。
- bootstrap从第一setup即监控shared job root；每setup同时核本地30min、reviewed build剩余、全job剩余，并计30s cleanup。
- archive实际输出在runs/archives/output，受512MiB本阶段树限；weights在runs/weights/output，受4GiB树限；reference在owner profile/actual/reference，supervisor实际run为profile/actual，受160MiB树限（含日志）。总12,081,306,272不变。
- reference CPU固定1200，RSS3GiB/AS8GiB，phase内128MiB写文件限不变；existing大权重仍可被2GiB只读watch观察，不降硬件。
- top controller/bootstrap/Python executable独立纳入准入pins。测试仅mock/元数据；没有证明标准runner实际20.67GBfree、CPU或完整M128 wall预算。
