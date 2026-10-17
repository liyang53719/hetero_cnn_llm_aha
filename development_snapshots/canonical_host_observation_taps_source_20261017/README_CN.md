# Canonical Host 三源观察逻辑历史快照

状态：SOURCE_ONLY。保存三个项目 Scala 源文件、对应 baseline 原字节和只增观察语句的 patch。Git 提交或发布状态不改变源码、CLASS、IR、RTL 与运行证据之间的边界。

## 内容和独立用途

- `candidate/`：已获 SOURCE GO 的 Qwen2Block.scala、FfnTileSiluBridge.scala、VectorSilu.scala；保持原候选逐字不变。
- `baseline/`：同三个文件的原项目基线源码，保持原字节；不含其余闭包依赖。
- `patches/`：原已审的三个项目补丁；仅描述这三个源文件的观察逻辑插入。
- `test_projection_cold.py`：新建、独立的纯文本冷测，只读本目录文件，不加载任何项目 Scala/Python 模块，也不使用编译器或运行模型。
- `PROJECT_SOURCE_HASHES.json`：只绑定上述项目源码、补丁和冷测源码。

原候选名称为 `production_canonical_host_observation_taps_source_v1_20261017`。本快照是独立、缩小范围的来源保存，不是其全部工作目录、执行环境或历史证据包的替代副本；既有 metadata 和公开许可问题不因保存本快照而改变。

## 冷测与反投影

在本目录执行：

    python -I -S -B test_projection_cold.py
    python -I -S -O -B test_projection_cold.py

冷测核验项目源 hash，按固定 patch 精确前向重放及反向投影，并要求每个 hunk 在字节层面只增加文字：删除新增观察文字后，全部保留源码逐字等于 baseline。冷测还检查九个声明束的源代码位宽，并拒绝变更原文、事件、patch 路径和非纯插入替换等负例。

这些检查是固定源码身份与文本差异的证据，不是通用 Scala 语义证明、合成证明或运行等价证明。小包中的 baseline 和 candidate 都不构成可独立编译的完整工程。

## 观察逻辑与资源边界

本轮三源合计九个命名组合观察束、2604 bit：

- Qwen：score117、prob113、cos593、sin593、PV request context81、PV ACK marker1，共1498 bit。
- Bridge：tile response590 bit。
- Vector：SiLU phase4 observation513、loan context3，共516 bit。

117 bit 仅是 score 单束，不能作为三源总量。新增语句不引入寄存器、状态、存储、读口、顶层端口或 MAC；原算术、状态推进和握手语句在删除投影后完全保留。2604 bit 是源码声明账，不是生成网表资源测量；组合选择、扇出与 dontTouch 仍可能有面积或时序代价。

prob 取真实 matrix request.fire 的 BF16 A0；cos/sin 取已 materialize 的 cv/dv。PV request 是待完成请求，内部成功响应 marker 不等于 AXI B 退休，仍需真实 tag/address/span 和传输上下文追踪。Bridge 需实际 canonical 实例配置、配对及 sealed/live 验证；Vector 需 resident loan 身份及 abort/poison 验证。仅有 tap.valid 不能证明整次操作成功或27节点覆盖完整。

## SOURCE、CLASS 与 RTL 必须分开

- SOURCE：上游三源候选已获独立 SOURCE GO；本小包只另做独立文本冷测。
- CLASS：同一组三源已参加另一次完整95源、全新 class 的真实编译，结果 exit0。该编译依赖完整95源闭包；本目录没有重跑编译，也不携带或声称独立拥有该完整闭包的 CLASS 资格。编译审查结论与最终资格应另行核验。
- IR/SV：本快照无生成、检查或等价证明。
- 实际捕获：没有真实 C++ 绑定、27节点 capture 或完整 block 数值通过。
- 完整 block RTL：仍为 0/5；CLASS 成功或 SOURCE 保存均不能提升这个数字。

本目录不含工具链、系统头文件或库的路径/版本/hash 库存，不含 JAR/JDK/class、原始进程日志、生成 IR/SV、权重或可重建权重 payload、canonical raw/reference 数组。没有带入先前未获许可包的其他内容，也没有修改原来源目录。

`INSTALL_MAP.json` 记录候选安装映射，不构成运行通过证据。实际安装或发布状态以仓库 Git 提交及远端核验为准。
