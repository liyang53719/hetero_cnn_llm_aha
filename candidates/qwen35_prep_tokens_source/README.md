# 内部 InputPrep 多 token：单源码候选

这不是完整 Qwen3.5 block、chunk64、公共命令或 RTL 的通过结果。候选只扩展 GdnInputPrepOwner 的内部顺序 token 外循环，默认 maxTokens=1；公共构造点、Host decode、descriptor 和 GdnRecurrentOwner 均不改。只有显式开启且 heads=16 的内部实例可接受多 token。

## 文件与复现边界

- `overlay/GdnInputPrepOwner.scala` 是新 owner 源码；`GdnInputPrepOwner.patch` 是相对固定 remote commit 的唯一生产补丁。
- `CONTRACT.md` 固定布局、别名、算术及 token ACK 边界。
- `INPUT_PINS.json` 固定原单文件身份及 remote commit，不含机器路径。
- `tests.py` / `TEST_SCOPE.md` 是纯 Python 源码比较和合成合同控制。它们不编译或执行 Scala，不提供真实硬件握手证据。
- `SOURCE_MANIFEST.json` 只封本批小源码，测试结果另封；不能用 manifest 的存在继承任何运行资格。

目标解释器为 CPython 3.12.14。测试运行命令在 TEST_SCOPE 中，原源码路径由调用方显式提供；不从本地 HEAD 推断固定基底。准备与测试不需要权重、参考数组、native 库、Scala 工具链或当前运行候选。

原 source 为 remote commit `adefaa78c2d313d9927b4e87550dddc926b3c605` 下的 `chisel/continuous_prefill/src/main/scala/heteronpu/continuous/GdnInputPrepOwner.scala`，13,048 B，SHA256 `86fa350cd87bc140b762db2deb5650c25e3b30bae4fb12cef7fe407e6b4faffe`。

## 保留和改变

原 Job/Result/Port、13 FSM 状态、16 算术操作、scalar 请求与结果顺序、数值拒绝、tag/error、done backpressure 和失败锁定不变。M1 token=0，原分离指针与小 heads 域保留。新增只有 maxTokens 配置、token 寄存器、固定 packed 地址项、M>1 admission 和末 gate ACK 的 token 外循环。

M>1 强制 heads16、recurrentMode=false、Conv/Core/AB 行跨度分别 12,288/25,600/64 B，完整 allocation 不越界且写区与所有读区不重叠。每 token 重读 AB→ALog→dtBias 三个原参数 beat，不复用 Python prep 的跨 token 参数缓存计数。

在完整成功轨迹上，每 token 195 读事务和 400 写 ACK，M128 合计 24,960 读、51,200 写、76,160 事务、3,276,800 写字节。当前这些是源码/合同预测，不是已执行的真实调度计数。

## 未完成项

尚未 Scala 编译、RTL 生成、实际 owner/native/模型执行或官方数值比较。仍需后续独立准入验证真实 request/result/ACK、M1 回归、多 token 中间值、stalls/错误与锁定、完整写覆盖。串行 prep 不证明吞吐或全块利用率，也不能替代 chunk64 三角系统、状态更新、公共多 token 接线。

当前其他活跃任务及冻结输入/证据不属于本包，不读取、不复制、不修改。本包不授权任何实际后四 block。
