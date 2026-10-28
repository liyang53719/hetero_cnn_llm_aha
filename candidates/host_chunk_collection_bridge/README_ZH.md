# TEMP：Chunk Collection 私有向量接口接线

**已通过：源码接线检查 + 10 份真实源码的 Scala 类型编译。未通过/未执行：Top 集成、Chisel elaboration、RTL、数值 DUT、五块完整 M128。M128 仍为 0/5。**

## 本批仅三处源码替换

`GdnRuntimeChunkLeafCollection.scala` 的 request/result 从 V2 改为私有 V5，实例化从旧 Execute 改为 `GdnRuntimeChunkExecuteOwnerV8`。源码 SHA256 为 `15798b8c3cba4522968e55b6a7f3306e5e5212b6b5abd8537ff9b5d38def7ca8`；逆向三处替换后与实际历史 Collection 字节完全相同，原始 SHA256 为 `8e52017144139161eed37eb8d635b601478ee3372ef1507e850afcbe35e9edaf`。

两条向量 request/result 是真实 Derived/Execute 叶模块的完整 Decoupled 连接，保留 `gradual`、`formatOnly`、`arithFlagsValid`。不通过 Bundle 强制转换、mode 常量或假完成绕过接口；五条 Memory、两条 Scalar、job/done、commit snapshot、fault/drain 和 route capture 均原样保留。不新增 bank/FPU/仲裁器/本地 RNE；本批不是物理资源报告。

四份 bridge 源码继续引用同仓库 `candidates/host_chunk_gradual_bridge`，固定在提交 `65cbbb3e92079a859e4d4d8509a6b4383ba690fc` 的内容；本批不覆盖该候选或现有 Top。

## 已有真实结果与本批复核

- 原始源码检查 normal / `-O` 均 135 checks，9 个错误接线变异全部被拒绝。
- 一次实际 Scala 2.13.16 + Chisel 6.7.0 compiler-plugin 编译：Collection + 四份 bridge + 历史 Coordinator、LoadPrep、Transpose、HeldOffer、State，共 10 份源文件。
- classpath 从上一批 903 类移除 9 个重编译家族，再加入 3 个真实历史类型，保留 897 类；输出 44 类，其中 Collection 7 类。无同名遮蔽或假类型。
- compiler exit 0、空日志，1,392 个前/后 pin 检查吻合。wall 32.59 s、采样 CPU 27.06 s、peak RSS 367,562,752 B；原始受控编译进程组已终止。
- 本批独立复核了真实历史原文、897 个基线 class hash、44 个输出 class 的 hash / internal name / SourceFile、全部 10 份源码与真实 receipt。只是读取和轻量源码/打包测试，没有再次运行 compiler 或 DUT。
- `ACTUAL_FACTS.json` 是有限范围摘要；`EVIDENCE_PINS.json` 仅给出原始本地证据 hash，非原始记录的完整公开副本。`CLASS_IDENTITIES.tsv` 只有身份/hash 元数据，没有 class 字节。

## 轻量复核与 requires-parent 边界

```sh
python -B verify_package.py
python -B -O verify_package.py
python -B check_source.py --parent-source /path/to/pinned/GdnRuntimeChunkLeafCollection.scala
python -B -O check_source.py --parent-source /path/to/pinned/GdnRuntimeChunkLeafCollection.scala
```

前两条需要同 checkout 的上一批 bridge，检查本包 allowlist/hash、依赖元数据增量和 inverse hash；不能冒充已取得原始 parent。后两条必须显式提供实际原始 Collection，缺少时失败退出。公开版检查为 110 checks / 9 个变异；相对原始 135，保留相同接线与变异检查，但把 30 个私有冻结文件 pin 校验改为 5 个公开候选/bridge 源码 pin 校验，**不把公开元数据检查冒充完整私有冻结复核**。

`SOURCE_PINS.json` 列出 10 份实际编译输入，五份历史源码标记 `requires_parent`；原始 Collection 也未包含在本批。`CLASS_DELTA.json` 使用上一批 903 类 pin 表和明确的 -9/+3 增量确定 897 类，只有元数据，不携带 class 字节或其完整源码构建闭包。106 个有序 JAR、compiler plugin 和 314 文件 JDK 工具树与上一批相同；不得从 metadata-only 推导 fresh hermetic reproduction。

`REPRODUCTION.json` 提供与原始 argv 逐项逆向核对的手工模板和资源上限；它不是可自动运行的 supervisor。取得所有 parent 输入、核对 pin、使用等价有界监督之后才能另行执行编译；本批没有触发该模板。权重/数据/依赖在本地或 CI 按需生成或恢复，禁止提交 local.npz、remote.npz、权重、class/JAR、IR/RTL、ELF 或文本编码的二进制载荷。

## 中文后续计划与未关闭项

1. **先关闭真实 RawPrep producer P → Chunk consumer C 的 ABI/来源绑定。** 两者 tag 不同；历史 Coordinator 第 171 行仍要求 `r.tag === c.tag` 和 `accepted.tag === c.tag`，且 Collection 仍接历史 `GdnRuntimeInputPrepResult`。本批完全保留检查，不伪造/重写 ACK，也不把几何、计数上限或 interface schema 当作 producer provenance。需按真实生产者完成与后续消费 owner 建立可审计绑定，再讨论接入。
2. **再关闭实际 Top/Kernel slot8 Scalar 与 slot10 Vector 的资源路由。** 本批只连内部 Collection；普通 Top 的 slot10、全局 lease/tag/epoch 归属仍未接好。上一批“旧 Collection 不兼容”仅在这个新候选内部解开，不能称整个旧 Top 已兼容。
3. 在上述证据闭环后，另作有界 Chisel elaboration / RTL / native DUT / 数值与协议验证；本批未运行这些阶段，也没有完整 M16/M128 或五 profile 通过。**五块 M128 Chisel/RTL 仍 0/5。**

准备期曾有两个小检查器假设错误，均未启动 Java；历史失败、原始文件和证据保留。本批只添加该候选目录，不覆写已有用户文件；不清理文件，不手动重跑 CI。
