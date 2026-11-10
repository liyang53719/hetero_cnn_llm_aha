# TEMP：原 Conv → RawPrep → 两个真实 chunk 的连接候选

本轮新增真实原 `GdnRuntimeConv4OwnerRecoveredV7` 接入先前 RawPrep/phase1–17 链，不修改任何上游 DUT。Conv 只在真实 output/history ACK、historyCommitted/status/drained 全部满足后交给 RawPrep；同一 scalar/bank/memory 被分时复用，没有软件算术替代硬件。RawPrep 的 Conv 输入不再预置，在读请求时要求存在实际生产者写入。

保持 n16 原 fatal-underflow policy 0；这不是 head4 gradual candidate，也不重跑其原任务。合成刺激改变，旧子链 PASS 不迁移。Dense QKV/AB 和 Conv 权重仍是可重建合成输入，没有真实权重、RMS/Dense 前缀或 GatedNorm/O/FFN 后缀；没有统一4096 MAC或五块完整block通过证据。

验证范围：
- Scala 编译 exit 0。
- CHIRRTL 发射/连接 elaboration exit 0，仅 IR，不是 RTL 数值 PASS。
- 独立 Python 冷态 tap 顺序/history 和零权重两个 unittest PASS。
- M128/head0 独立参考生成 exit 0；25474 初始读beat、104320预期写beat。Conv 额外25344读/25344写beat，Conv输出与history均不在初始内存中。
- 未运行新候选硬件数值回归。完整五块仍 0/5；无完整block有效MAC利用率实测。

复现轻量步骤：
```
python -m unittest test_conv_reference -v
python generate_fixture.py --head 0
python compile_only.py --jar-dir /path/to/pinned/jars
```

下一步：先对新连接做真实硬件数值执行，需单独评估预算（786432个Conv元素、每元素13个共享scalar请求及2次格式物化，原run.py默认8M cycles不足；不得将预算不足说成数值FAIL）。之后换真实Dense投影生产者及权重并续接尾部。未把单scalar功能链当90%性能方案。

本目录生成输入、期望、CHIRRTL、class和依赖留本地；源码包只含代码/pin/hash/摘要，不含这些可重建数据。原head4未知终态证据不改不删。

收尾修正：Conv所有终态由独立convReported暴露；driver每周期遇resetRequired立即abort，Conv非零status/未commit立即FAIL，不等cycles上限。参考入口dtype/shape使用显式ValueError，python -O下错误dtype拒绝已验证。修正后重跑两单测、Scala编译、CHIRRTL elaboration；未运行硬件数值仿真。

## 本轮执行（INCOMPLETE）
已启动M128/head0原Conv→RawPrep→两chunk真实数值跑，120M cycles/3600s wall/3300s CPU有界；尚无终态不得称PASS。原n16 fatal0保持，原全16下溢FAIL不迁移。

首次真实仿真 exit1/cycle2：driver先观察resetRequired再撤销已消费response.valid，看到未采样的组合unknown暂态。已保存原失败，修复为每轮先驱动响应再观察输出，保留fault检查，未改DUT。修复后仅重新编译，尚未重跑数值或重新发射IR；之前CHIRRTL只对应修复前候选。
