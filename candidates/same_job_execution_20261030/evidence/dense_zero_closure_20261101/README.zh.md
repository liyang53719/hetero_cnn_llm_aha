# Dense 全零清除构造：候选存储转换的局部 AST 资格

当前候选原Top的 HIGH、官方LOW和canonical已在远端通过；后续 Dense 兼容转换报有限 DENSE_ACC_LOCAL_SHAPE。尚未取得本次新HIGH正文，不能把某个具体 require 当作已观测远端原因。

旧转换硬写两个自动 `_WIRE` 名。新候选版本不猜新名字：必须证明2个不同Tile Wire、32个不同Row Wire、8192个精确UInt<32>(0)，唯一命名/驱动/消费、同Block且早于原bulk write；原131072bit容量、16并行writer、零延迟read、3写优先级、全部索引与其余AST不变。旧生产类原样保留。

## 实际局部证据
- 1133编译4个生产helper，最终1140只重编fixture并复用这些逐字节相同的class；各阶段原1GiB/60CPU/90wall，7GiB准入与8GiB磁盘门，不扩资源。
- 官方Parser先核保留的历史Core完整canonical；新旧转换结果完整AST、serialize、canonical均相同。只对34个零构造wire改名后，新转换结果完整AST等价，旧固定名字转换明确拒绝；10个坏例全部按精确predicate拒绝。
- 初次Block无Info的Scala API错误及alpha fixture错误均保留。实际证明generic Block.mapStmt会扁平化已插入Block但serialize不变；仅fixture改显式copy保嵌套，最终完整AST断言没有降低。
- 不是新实际HIGH形状已通过，不继承历史部分运行PASS，不是DUT/五块数值或最终RTL验收。

## 复现材料边界
唯一fixture源码在 `candidates/model_candidate_build_20261101/CandidateDenseStorageFixture.scala`。`extract_prior_core.py --input ORIGINAL_HIGH --output NEW_FILE` 仅流式抽取并核固定历史5,839,431B/SHA；原HIGH需从保留证据取得，不下载、不发布它。随后使用同pinned FIRRTL2/JAR与4个生产helper运行fixture（编译/AST进程必须另行有界监督）。本目录不包含原IR、classes、rawlog、权重或参考。
