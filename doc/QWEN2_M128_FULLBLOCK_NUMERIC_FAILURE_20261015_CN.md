# Qwen2 M128 完整软件链数值失败与下一步（2026-10-15）

## 当前结论

同次 fresh M128 public21 完整软件链已实际执行到 whole-block terminal 和 finalfence，并完成官方参考比较。验收结果仍为 **FAILED**：24个原数值门中20个通过，scores、logits、prob、FFN gate 四个门失败。最终 y 通过原 block 门，不能覆盖中间 producer 失败或升级整链通过。

- 执行源码提交：`58034f794df1322d5c4493622411862e2a66c77d`
- 执行源码摘要：`50df1ca46da69da30009b30c6ff69799f9ba2f0cd0cd06300c7873eb116b88d1`
- [实际运行 38696907327 / job 116295518943](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/38696907327/job/116295518943)，原工件编号 `11956497199`
- 本文记录已独立审查的固定聚合与状态，不修改原失败回执，不重跑DUT，不发布逐输出明细。

## 已建立的完整链边界

21个 public completion、17个 owner job、1个 accepted launch result 均核验通过。同一 live execution、memory、services、owner、banks 身份保持，后端债务归零；完整终态、finalfence、cache 精确 copy、来源未变、结构和资源门通过，实际输出已 seal。数值失败导致 acceptance 未 seal、完整 block 通过标志为 false。

这是本次完整软件执行的新事实；历史 pc8/pc12 held、预算超时、guard 拒绝和 posthoc 限定通过分别保留。历史只读后验比较不变成本次运行通过，本次终态也不回写历史运行。

## 原数值门与失败聚合

原 operator 门为 max_abs ≤ 0.03125、mean_abs ≤ 0.005；原 block 门为 max_abs ≤ 0.05、mean_abs ≤ 0.01。两者均不放宽。

| 门 | max_abs | mean_abs | 原门结论 |
|---|---:|---:|---|
| Attention scores | 8.0 | 0.0005980499031007752 | false |
| Attention logits | 8.0 | 0.0005980499031007752 | false |
| Attention prob | 0.031494140625 | 0.0000007151029234076358 | false |
| FFN gate | 0.041015625 | 0.00005037509903494148 | false |
| 最终 y | 0.03125 | 0.000041511200834065676 | true，仅最终 block 输出门 |

scores 与 logits 共用同一个 `scores_bf16` 观察字段，比较覆盖99072个因果位置。四个失败门对应上述观测，不能解读为四个独立根因，更不能把 scores/logits 当成两个独立DUT异常。未来位置不补作DUT观测；当前证据不是完整29节点DUT验收。

其余20个数值门为 true，包括六个 prefix producer、PV/att、除 gate 外的尾部节点、cache K/V、official KV 及 softmax 行和。通过意味着达到各自原门，不自动代表逐bit相等；当前还未分清局部算术误差与上游误差传播。

## 平台参考和 cache 合同

本次参考合同为 `official-ast-ci-aten-avx2-reference-v1`：在同一 runner 上两个 fresh 完整 capture 字节一致，实际 libpython 边界已核对。这里的字节一致限定于这两个平台 capture，不能推成与历史平台参考相同，也不代表执行了完整官方 forward。运行中比较使用冻结参考，不把参考算术混入DUT执行。

cache 合同为 `sealed-same-live-cold-cache-v1`。同次 live K/V 到 cache 的 copy 精确通过；官方 cache 数值比较按原阈值通过。copy 精确与官方逐bit一致是不同结论，本次不宣称后者。

旧平台/guard/预算等失败原样保留，不将曾被拒绝的 metadata 改名后充作新来源或验收证明。

## 性能与硬件边界

- host wall：2240.388901111 秒
- useful MAC：6,014,828,544
- executed MAC：6,598,164,480
- useful/executed：0.9115911799761621，属于软件操作效率
- hardware cycles / utilization / duty：均为 null
- RTL executed：false

软件操作效率、进程秒数和功能事件不能替代完整 launch-to-terminal 硬件周期。固定 Matrix4096 和实际 Vector/Scalar 库存分母保留，不按活跃 lane 缩小分母。CPU候选未因此修改 Chisel 源码；真实算术RTL、完整资源库存和完整周期性能仍待验收。

阶段优化下限80%、争取90%；最终硬验收仍要求同源实际完整RTL数值通过且固定资源完整周期有效MAC利用率至少90%。不以软件0.911591或局部RTL门宣称达标。

## done / ongoing / to do

以下是唯一清单中的阶段进度摘要；任务状态仍以 `block_checklist.yaml` 为准。

### done，仅限已记录范围

- 同 runner 两个 fresh 平台官方AST参考 capture 字节一致及实际 libpython 边界复核
- 完整 M128 同次 public21 软件链终态、官方比较和协议/来源/资源聚合核验
- 四项原数值门失败及最终 y 门通过事实登记和独立审查

这里的 done 不表示完整 block 数值通过，不关闭任何父任务。

### ongoing

1. QK/prob：独立复核相同输入局部算术对照与上游传播隔离，未审细节不提前定为根因。
2. FFN gate：使用相同 n1 输入隔离 gate 局部算术与前级传播。
3. 独立 Q/K 归约候选设计与固定4096资源成本核对；尚不形成硬件结构或收益结论。

先完成有界小链及独审，形成可审查修复后，再决定按冻结来源、原门与预算复验完整 block。不盲跑全链，不从保存中间输出冒充 fresh 整链，不用最终输出通过掩盖中间失败。

### to do

1. 修复后重新闭环 Qwen2 M128 完整链的原数值门。
2. 冻结已通过激励，接入真实完整RTL，补齐资源库存和完整周期性能验收。
3. 按顺序推进 Qwen3.5-0.8B L0/L3、Qwen3.5-35B-A3B L0/L3。后四个 block 本轮未推进，历史进展与失败保留。
4. 更长1024或1224的准确范围待澄清；不阻塞当前128，128也仍未验收通过。

`U00.2 ongoing`、`U01 to do` 保持；46个父任务和全部叶项状态均不变。五个 block 的完整实际RTL与90%联合门仍 open。

## 文档验证边界

本次只同步中文计划、唯一清单的当前进度和本文；原任务数组、状态、数值门、RTL目标及历史证据不改。计划字节变更已同步清单中的计划 SHA256。只读视图的自动生成表前缀与原工具输出一致，无需改写；其后已有的历史附录保持原字节。

精简检出缺少一个历史已登记的压缩日志，改动前完整清单证据验证已拒绝。缺项如实保留，不伪造证据、不清除原 done；本次文档结构/状态/hash 一致性检查与该历史全证据检查分开报告。上述验证不等于数值重跑或RTL执行。

本次短测使用既有 `tests/test_typical_block_plan.py` 与 `tests/test_block_checklist.py`，普通 Python 和 `python -O` 均为90项通过、1项相同历史缺证据失败；优化模式另有 pytest 的断言优化警告。命令为 `python -m pytest -o addopts='' -q tests/test_typical_block_plan.py tests/test_block_checklist.py`，优化模式在 `python` 后加 `-O`。

单独的 plan validator 通过；明确不检查历史证据文件的结构验证通过，并另外核对当前 plan hash、两份任务数组与基线原字节、自动表前缀、历史附录保留和本次固定聚合。全量登记文件扫描只有同一个历史压缩日志缺失，已存在的登记文件没有 hash 漂移。该结构验证不替代被拒绝的完整证据验收。
