# Production kernel QKV reduction：默认关闭的小候选

## 本次结论
候选 v2 的源码冷测试普通与 `-O` 各 13 项通过，包含 35 项生产接线片段缺失突变检查。独立复核后，对完整 91 Scala 闭包执行且仅执行一次有界 class compile：exit 0、545 classes、34.469 秒，原 leader 保留至严格 cleanup 证明完成。该结果仅证明 Scala 类型/源码编译，不能证明 Chisel elaboration、握手/组合环、RTL 数值或性能。

v2 patch SHA256：`d277217369cd80bd0f2e5b8b7f9740e29802de0d4981ca5d9c3636cf9c2a03cf`。

## 集成范围
原 HostBlockTop → QwenOwnerKernel 中增加默认 `false` 的 `enablePublic21QkvReduction`。PC 1/4/7 的 Public21 Dense 使用既有 coordinator，依次执行 `[0,1024)`、`[1024,1536)` 两个 raw FP32 partial，pairReverse=true，经唯一共享 SFU/vector Add 再真实 drain。既有公共 Bias/BF16 后处理仍独立执行。

保持唯一 Dense/Matrix4096/SFU16/iDMA 及原 bank 集合。新增 router 为内部控制，不是新顶层。ordinary active 只由 ordinaryJob.fire 设置；resident 请求/返回条件保持。binaryAdd 参数透传到既有 ScheduledSiluOwner；resident binaryAdd 与 kWindow.enabled 显式 false。真实 Matrix/seed/read/write/nonburst 债务均按 ACK 退休，abort 不清空债务。

资源账本见 RESOURCE_LEDGER.json：源码声明新增 1987 bit，其中 lhs 保持寄存器 512 bit（64B）、控制/metadata 1475 bit，不是综合结果。lhs 必须跨第二次共享单端口读取及 SFU backpressure 存活，未增加第二份 payload FIFO 或算术 bank。

原 Attention 仅功能基线候选，约 48.2% ideal 上界仍远低于完整 90% 目标。完整 M128 同刺激 RTL 数值、29 mask/FP32 tolerance、原 Attention 吞吐、SFU 优化均未关闭。

## 可复现源码与冷测试
以下 `$CANDIDATE` 是本目录，`$CHECKOUT` 是满足 MANIFEST 固定源身份的仓库；不同 commit 但字节不符会失败，禁止自动刷新 pin。replay 只向新的 `$WORK` 输出，完全不修改 checkout。

```
python -B "$CANDIDATE/replay.py" --source-root "$CHECKOUT" --out "$WORK"
python -B "$CANDIDATE/test_cold.py" --source-root "$WORK"
python -B -O "$CANDIDATE/test_cold.py" --source-root "$WORK"
```

`--repo` 仍作为 `--source-root` 的兼容别名。test_cold 的 source-root 指 replay 产物目录，其中有 baseline/ 与 source/；不指定时取候选目录的 composed/。default_projection.py 仅为 false 分支源码归一化检查，不宣称 RTL 等价。

## 便携 class compile 入口
包不附 jar、classes、HardFloat 大源码树或机器绝对路径。71 个 Scala 来自候选 77 文件（其余 6 个 SV 不执行），另 20 个 HardFloat 构成精确 91 闭包。`$HARDFLOAT_SCALA` 指含 AddRecFN.scala 等文件的目录。

```
python -B "$CANDIDATE/compile/prepare_sources.py" --source-root "$WORK/source" --hardfloat-root "$HARDFLOAT_SCALA" --out "$COMPILE_SOURCE"
python -B "$CANDIDATE/compile/compile_only.py" --preflight-only --source-root "$COMPILE_SOURCE" --cache "$PINNED_JAR_CACHE" --java "$PINNED_JAVA" --output "$FRESH_OUTPUT"
```

去掉 `--preflight-only` 才会启动编译；再次执行须获得单独批准。仅 scala.tools.nsc.Main，1GB heap/1 CPU，入口统一 88 秒，包括前置验证与复制；work deadline 80 秒，最多 8 秒 cleanup，postflight 使用原 stop 剩余时间。classpath 仅 87 个 pin jar，无旧 classes；输出目录必须全新。无 emitter、sbt、elaboration、RTL/EDA 或数值执行路径。

原执行 launcher SHA 与便携参数化入口的区别列于 evidence/compile_identity.json；便携入口仅冷预检通过，没有另行编译。完整 class hashes 与去标识化 cleanup 证据投影见 evidence/class_compile_receipt.json（不是原回执字节，原回执 SHA 保留，本机保存原件）；不附临时运行日志或 raw classes。

## 历史失败与边界
v1 patch（SHA `e23548484691829b5f6dd20079dfb80a17e66fdbbe0acea9e53ff599bfa16d67`）已废弃：held-success 遇晚 abort/backendReset 时同时屏蔽 valid/ready 导致 waitDone 死锁。v2 保持 terminal payload 与握手，原 HostBlockCommands 在同拍 resetRequired 将成功转 Protocol，sticky fault 禁止重新准入。该源码修复已独立审阅；还没有实际 RTL trace。

既有 KWindowTests/DenseDrainTests/PublicCoordinatorTests 共 34 项 normal PASS；同组 `-O` 有 18 error，因为旧测试将推进状态的 tick() 写在 assert 内，优化模式删除它们。未改历史测试，也不将其 -O 失败算作候选 PASS。本包自己的 13 项普通/-O 均通过。SOURCE 字符串及独立 Python 控制模型不等于真实硬件协议验证。

打包时尚未 push/发布；本次工作没有完整 elaboration、RTL 或昂贵数值任务。
