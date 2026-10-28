# TEMP：Chunk 私有 gradual 模式桥接；仅四源 Scala typecheck PASS

**不是共同 Top 安装，不是 elaboration、RTL 或浮点数值 PASS。五块 M128 Chisel/RTL 仍为 0/5。**

## 本批完成

`source/` 四个 Scala 文件与实际编译输入逐字节相同。V2 policy 仍只有 0/1/2，raw3 仍是诊断 BF16 运算加错误；不把缺失的 `UnifiedVectorPolicyV2.RawFp32FiniteGradual` 草率补成 3。

私有 V5 包装新增显式 `gradual` 位，与 `formatOnly` 互斥：gradual 只能携带 policy0，映射到现有物理 V4 policy3；format 只能 policy0、非乘法且 b 全零，映射 policy4。回复模式来自保留的物理 policy/tag，不借用实时请求；实际低 16 路 FP32 值及五位 flags 直接传递。旧 vector 路径、单一 fixed32 V4 bank、标量端点及捕获/计数/lease/retire/drain 主体未改；未增加本地 FPU、格式器或寄存器声明。高 16 路仍是真实零操作数，不是 lane mask。

已观察到的验证（详见 `ACTUAL_FACTS.json`）：

- 普通/优化 Python：107/107 source/pin 检查，拒绝 9 个故意破坏的源码变体；11 个纯契约测试，64 种模式组合中 21 合法、43 拒绝。测试使用不透明哨兵，不计算浮点运算。
- 实际 Scala 2.13.16 + Chisel plugin 6.7.0 编译：四源、903 个保留依赖 class、17 个新 class / 508505 字节；编译器与外层退出均为 0，日志为空；1375 项输入前后检查通过，输入/冻结源未改。
- 903 = RawPrep 原 904 − 被替换 protocol/adapter 9 + 原 Chunk 支撑类 8。`CLASS_SCOPE.json` 保存删/加/新类的名字及 hash，`BASELINE_CLASS_PINS.tsv` 保存完整 903 项 identity；不发布 class 内容，也不加入伪造的类型定义。
- 22.451 秒墙时、18.51 秒采样 CPU、319631360 字节峰值 RSS；有原编译组终止/回收证据。本次打包不再次启动编译器或 DUT。

## 可复核与不可复现的边界

本包是 **requires-parent**，不是自包含、一键或已重验的完整复现环境。四源、测试及 pins 可公开检查；903 个依赖 class 的原始 source/build closure、完整 314 文件 JDK 闭包以及历史监督器仍须从父依赖记录另行恢复。仅有 hash 不表示这些输入已公开或可下载。

轻量检查（在本目录）：

```bash
PYTHONDONTWRITEBYTECODE=1 python verify_package.py
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -v
PYTHONDONTWRITEBYTECODE=1 python -O verify_package.py
PYTHONDONTWRITEBYTECODE=1 python -O -m unittest discover -s tests -v
```

完整历史 107 项 source guard 另需外部精确父输入：按 `BASE_PINS.json` 的相对别名放置原文件，令 `CHUNK_PARENT_INPUTS` 指向该根，再运行 `check_source.py`（普通及 `-O`）。缺失父输入会失败，不会静默降级。其检查逻辑原样保留，仅根路径绑定可移植化并已逆变换核验。

`DEPENDENCY_PINS.json` 给出有序 106 JAR 与 plugin hash；`REPRODUCTION.json` 是原命令的路径角色化手工配方，逆变换与原 argv 完全一致。配方不是可执行的资源监督器，不会下载、自动编译或运行设计 main。父闭包未补齐前不得声称已从本包复现编译；不同机器的 CPU affinity 还须单独评估。`EVIDENCE_PINS.json` 只给出原记录身份；原记录含私有运行路径，不上传。本地原件、原冻结内容和既有失败全部保留。

## 中文后续计划与当前阻塞

1. **P0：共同 Collection/Kernel/Top 尚未接通。** 旧 Top 没有 ordinaryVector slot10 请求/结果及 authority/retire 接线；旧 Collection 暴露 V2、直接接 Derived 并实例化旧 Execute，不兼容新私有桥。下一小批需审查真实 successor，将 Derived/Execute 向量接 slot10、标量接 slot8，并接实际内存客户端。旧 Execute 的本地 32 个格式器尚未从共同 Top 移除。
2. **P1：真实 RawPrep producer-ACK 到 Chunk owner 的来源链未闭合。** 保留成功 producer receipt 和已接受元数据，producer tag 与后续物理 owner tag 必须独立；禁止靠几何/计数上限推断成功或改写 receipt。
3. 父依赖闭包及真实调用者接线齐备后，才分阶段做共同源 typecheck、Chisel elaboration、协议/RTL 仿真、真实 FP 数值及 M16/M128 五 profile 验证。当前只编译四源，Scala typing 不能发现所有 Chisel 未接端口/批量连接问题。

没有 full-host、物理 SRAM、PPA/QoR、吞吐/II、stall 时序或全数值等价结论。仅发布源码、测试、pins/hash 和摘要；不含权重、NPZ、JAR/class、生成 IR/RTL、ELF 或任何变相编码的可重建负载。
