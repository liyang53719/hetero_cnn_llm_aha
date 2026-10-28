# TEMP：RawPrep producer P → Chunk consumer C 原生回执候选

**只完成源码契约与一次真实 Scala 编译；requires-parent，不是完整复现包。**
五类完整 M128 Chisel/RTL：**0/5**。旧源码、失败记录及原有公开候选均不改写。

## 这次完成的边界

- 五份源码原样公开：Kernel 在真实 RawPrep `done.fire` 发出完整结果；原有 ready/valid 路径不变。
- Prefix helper 从真实 Guard 保留的 transaction/host epoch/物理 producer P 与真实完整结果建立快照。成功、committed、完整输入及字节数须精确匹配；Scalar8/Format9 真实退租和 borrower drain 后才 eligible。
- 快照是 Valid，不是 held Decoupled offer。fault、reset、上下文变化或真实 replacement 使其失效；replacement 同一拍也禁止可用。有效首个 P=0 不被误拒。
- 新 native V8 经 Collection 到 Coordinator；消费时检查 txn/epoch/P、完整 accepted payload 与 C>P。保留 producer 标签，不能把 P 伪改为 C；成功消费记录 txn/P/C，拒绝 replay、owner 复用及回退。
- 后续 leaf issue/return/fault/drain/held-terminal 代码保持不变。没有新增 payload bank、算术模块、arbiter 或 DMA。1,913 bits 只是声明宽度算术，不是综合面积报告。

## 实际证据与限制

- 冻结源检查 normal/-O 各 **1,172**，拒绝 **21** 项源码变异；Python 契约模型 normal/-O 各 **11** 项，不是 DUT 仿真。
- 唯一一次 Scala2.13.16 + Chisel6.7.0 plugin：**17 真实源码 → 86 classes / 3,081,279 B**，exit0、空日志。来自897的父类基线去除39重编家族，剩 **858**；848重叠旧 RawPrep 类无 hash 冲突。
- preflight/postflight **每轮1,382** pin checks；52.019s wall、43.99s sampled CPU、548,409,344B peak RSS。发布阶段不重跑编译器。
- 独立审查结论由协作消息传回，原实现者记录摘要；不是伪造的独立文件。原始私有证据仅发布 hash/大小绑定。

## 未完成，禁止据此宣称整块通过

1. 未变更的 Top **没有 Chunk dispatch、真实 accepted C/txn binding，或 snapshot → 一次性 held Collection prepDone 路由**。
2. 快照没有 Top consumer，可能被优化掉；未证明 elaboration 后确有 retained hardware。未来 parent 必须观察真实接受、保持已发布 payload 直至晚到 fault 处理完毕，并禁止重复消费。
3. 全局 Scalar8/Vector10 lease/tag/epoch 路由、Top drain/publication 仍缺失。
4. 未运行 Chisel elaboration、CHIRRTL/RTL、native DUT、数值/协议 M16/M128、综合及 QoR；不继承历史编译或硬件资格。

## 小型复现入口

```sh
python -B verify_package.py
python -B tests/test_receipt_contract.py
python -B -O tests/test_receipt_contract.py
python -B check_source.py --parent-source-dir "$EXACT_ORIGINALS"
python -B -O check_source.py --parent-source-dir "$EXACT_ORIGINALS"
```

`SOURCE_PINS.json` 区分5个随包编译源码、12个未随包的父编译源码，以及10个原版本源码检查输入。
`REPRODUCTION.json` 是与原命令逐项逆映射验证过的手动编译模板，**不是一键脚本或新运行授权**。
父类858项的完整 source/build closure、JDK314文件及 bounded supervisor 未随包，不能把本目录称为 fresh-checkout 完整复现。
工具依赖复用已公开的 pin 元数据；所有依赖、权重和运行数据只在本地/CI 按需恢复，不提交 NPZ、class/JAR、IR、SV、ELF 或文本编码二进制。

## 下一步计划

先设计真实 Top 接受的 C 绑定与单次 held receipt 交接，保留晚到 fault/drain 和所有权边界；再接全局 slot8/10 路由。
每一步先做源码/协议负例和独立审查，取得相应运行条件后再做分层 elaboration/RTL/numeric。
仍维持共用4096资源边界，不凭源码元数据扩增物理资源，不用假 ACK、fake consume 或抽象模型代替 DUT 证据。
