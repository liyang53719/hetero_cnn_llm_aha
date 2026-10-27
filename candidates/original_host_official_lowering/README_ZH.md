# TEMP：原 Host 官方 high→low 与有限结构检查

本批记录原 `HostBlockTopV4` 固定 public21 构造完成官方 high→low 流水，以及初始化、宽度/流向和组合环检查；不是五块数值回归通过。五个 profile 的完整 M128 验收仍为 **0/5**，runtime profiles 1..4 仍封闭。原始 Qwen2 的 M16/M128 能力不等于统一五 profile 接回已完成。

## 已发生事实

- 1044 单次实际 native/outer/reap 均为 0，13 阶段记录完整，14 产物；9 条 warning 保留。CPU 143.47 s 与 RSS 2,534,420,480 B 是采样口径；内层 wall 173.4908976299921 s，外层 173.58745102200191 s。
- high 69,399,011 B；两份 low 各 198,822,491 B。仅发布 hash，绝不上传 IR。两 low 相等来自原批准 runner 成功路径和完整产物 hash；独审没有再次遍历约 398 MB low。
- high 1040 定义/1040 可达实例；low 79 定义/1040 可达实例。8 endpoint ×512 的固定逻辑 Matrix 容量仍是 **4096**；共享 Vector bank 为 32 lane。还存在 **16 个 legacy BlockScalarFloat +1 个 PolicyV2 Scalar**，不能称整个 Top 已成为单 Scalar 或全构造统一资源解。
- Launch 为 25 个展平字段、844 payload bit。不是 SV、provider RTL、DUT/MoE 工作负载、reset/stale-epoch 恢复、物理 SRAM/面积/时序或有效 MAC 利用率证明。
- 1402 前后检查、883 类身份（仅 hash 元数据）、父门及严格 owned-group cleanup 已由独审绑定。此公开重建说明不等于新的完整动态运行闭包资格。

## 历史不能覆盖

0926 missing-ready FAIL、0951 两个组合环 FAIL、1023 CPU cap INCOMPLETE，以及 1031 输出 cap 且 owner/cleanup/inner-postflight 证据缺失 INCOMPLETE，全部保留。1044 的完整收据不补写 1031 历史；本批未混移动 runtimeNorm、Host 模拟适配、seed 后继或新数值结果。

## 最小可恢复源码与选择

`SOURCE_SELECTIONS.json` 给 47 个源码版本身份：33 个新普通 Scala、8 个已公开 exact source refs、6 个历史版本由最终源码加可逆文本 patch 恢复。只读 helper 按 hash 验证全部版本，不编译目标。**不可把 47 版本一起编译，也不可把同名旧/新类 root 全量合并。**

复现顺序是公开原始 source recipe 恢复 557 +已发布 preserved68→625；按既有已公开 MoE19/Vector 选择恢复必要 provider；依次 0735（559+102）、0855（724+156）、0915（880+3）、0943（876+4）、1012（874+9），最后严格选择 883 类给 1044 main。`CLASS_SELECTIONS.json` 的整数仅索引明文 class-name/size/hash 元数据，不包含任何 class 编码。原 20 个 HardFloat 外部源仍按既有固定官方 source recipe 恢复，不能省成 opaque class 依赖。

`REPRODUCTION.json` 保留 6 阶段历史 argv/cwd/env/caps 的逐项角色投影；私有根与 `${SOURCE_<SHA前12>}` 替为可恢复角色，106 JAR 沿已公开有序 lock。需要分别解析源码阶段、原两个 Maven 根/顺序和 baseline staging。它是**复现材料，不是可直接执行的原 launcher，也不是新的 hermetic runtime admission**。实际重建需另做工具/依赖身份与资源准入；本批不自动执行任何 JVM/EDA。

只读小检查（仓库根已有对应固定公开 refs）：

```sh
python -I -S -B candidates/original_host_official_lowering/rebuild_metadata.py --repo-root .
python -I -S -B candidates/original_host_official_lowering/test_rebuild_metadata.py
```

## 当前中文执行计划（不改变 canonical 74 项状态）

1. 继续五块原始 Chisel 完整 M128 数值并行推进，补齐真实 runtime profile、父授权和 feeder/retire 接回；未完成不得标 done。
2. 数值完成后冻结同源码、输入与官方参考，再生成同固定 4096 硬件、同接口/RTL hash，回放全部五块。结构 lowering 仅是此链的前置证据。
3. 32-lane Vector/Element 与原 4096 Matrix 分开；全链多在途、tag/credit、跨 tile cache、exact Div/sqrt/BF16 RNE 和所有五块必须重验，旧 16-lane 结果不继承。
4. 本批只保留已实际源码/结构与失败归因，不添加未测 runtimeNorm、Host 适配或 seed 实现。
