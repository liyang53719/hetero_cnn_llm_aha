# Qwen2 已有组合路径与控制交接进度

整体：**INCOMPLETE**。本片没有发现需要修改生产实现的差异，交付的是复用
真实 recipe 与既有控制模型的可执行证据，不是新架构或完整 prefill 数值结果。

- [x] 执行原 production replay：77 源文件。
- [x] 执行原 QK donor compose：13 源文件。
- [x] 执行原 QK16 builder：5 个 postimage 全部与既有 pins 一致。
- [x] 验证计划闭包中 72 个仓库 Scala 文件；20 个外部 HardFloat 正文未验证。
- [x] 17 个控制例覆盖尾块长度 1..16 及 token127/base112，held result 保持、
  scalar ACK 阻塞、score 一次提交、result/done/completion 各一次。
- [x] 对应真实 !packedBusy→attNextKey→attExpRead 门；原逐头 softmax/PV
  至 attPVStart 的路径存在且逐字保留。
- [x] 24/24 normal 与 24/24 -O；含隔离 CLI 冷启动，没有模型数值、Scala、RTL、
  native 或 CI 执行。

关键澄清：裸主线 `9572763a…` 与 production postimage `31b61868…` 不同，
是既有固定 recipe 的预期结果，**不是缺失生产架构的证据**。
已有 M128 Python 路径也有 Scala 来源 hash，但不运行这份组合后的 Scala。
不得从较早静态小门的 MISMATCH 推导出需要重写 Qwen2Block。

未关闭：Python 六头 packed 调度与 production 逐头 continuation 的真实操作
对应关系，shared-bank ACK/release、384B panel、PV6 retention、所有最终债务、
Scalar policy 和 full29。完整 92-source 编译闭包也没有在此重新验收。

下一片仍沿已有 `portable_same_host_m128_launch` /
`attention_packed_m128_same_host` prefill 路线，先把已选择 production 源闭包与
Python 原 owner/Matrix/Scalar 的实际入口、事件和数据布局逐一对应，在发现
明确差异后只改该差异。没有差异时应补最小证据，不虚构新 row service 或宽泛
重写。历史真正 cold M128 assigned27 PASS 保留但不继承，17 个控制例不得冒充
完整 M128，更不能用两个 M1 或单 token 循环替代。

详细复现、源码链与边界见
`candidates/qwen2_composed_handoff/README_CN.md`。
