# U00.2：Q/K 每头256维 Norm与packed gate候选组件

本轮只关闭可独立验真的Q/K Norm256和每头packed Q/gate布局门禁，不把官方投影值回放叫作Matrix producer接通。候选复用已有 `fp32_rmsnorm256_chunked`，编译参数默认0保持旧FP32直接weight语义。独立包装器只有明确policy 0xc1才执行候选；生产精度策略没有切换。

## 已审计的算术和真实几何

- 官方0.8B hidden=1024，Q投影4096按8个连续的 `[Q256, gate256]` 分组。不能将整个4096切成全局Q2048和gate2048，也不能误用hidden1024作为Q宽度。K为2个256维head。
- 官方Q/K RMSNorm先把BF16权重升为FP32，再做FP32 `1+weight`；gamma必须保留FP32。epsilon为FP32(1e-6)，bitpattern 0x358637bd。
- 保留的Continuous串行Norm使用元素顺序求和、HardFloat sqrt再divide；本轮复用的chunked256采用16元素平衡树，再按chunk顺序累加16个部分和，最后使用既有PWL表及一次Newton。二者不能互作bit-exact oracle。
- 实际Matrix输出context按递增K执行BF16×BF16+FP32融合累加；256输出列分成8个32列slice，并非split-K。Continuous写FP32输出，而本轮输入是冻结官方BF16投影，Matrix到Norm还缺明确FP32→BF16 producer边界和独立验真。
- 旧chunked内核在更新最终sumq之后才采样mean/epsilon异常位，其组合sum_next会再次加最后chunk。候选需在最终reduction握手时与mean_eps一起捕获对应flags；默认旧行为不静默改变。

官方来源为固定 `config/upstream/qwen3_5_0p8b/modeling_qwen3_5.py` 的attention及RMSNorm；串行路径为 `chisel/continuous_prefill/src/main/scala/heteronpu/continuous/Qwen2Block.scala` / `BlockFloat.scala`，Matrix顺序见 `StreamingDense.scala` / `MatrixPipeline.scala` 和 `integration/gemmini/EmitHeteroBF16Fma.scala`。

## 候选合同

完整合同见 `config/upstream/qwen3_5_0p8b/qk_norm256_candidate_contract.json`。输入一次只包含一个完整256维head，Q的高256个BF16为原始gate，K高半部明确忽略并输出零gate。gate不做浮点转换、NaN规范化或sigmoid，也不贡献异常位。输入捕获后所有权保持到结果握手；没有可排队tensor command。

算术逐步为：FP32 square → 每16维四层相邻归约 → 16个chunk自+0顺序累加 → FP32乘1/256及加epsilon → 既有一次NR rsqrt → FP32 x*inverse → FP32乘实际计算的gamma → BF16 RNE。没有FMA替代这些分开的操作，也不假设CPU native reduction树相同。

只接受signedzero或BF16 exponent95..158的x/weight，拒绝其他有限范围、非有限算术输入及不支持descriptor；gate/padding允许任意16位。该有界范围覆盖全部冻结真实输入，保证既有rsqrt的正常域，不能泛称全BF16输入支持。数据、tag、status、flags和debug标量在背压时稳定；复位丢弃在途结果，已完成计数清零。

## 来源与验收边界

默认门禁重新执行固定官方 embedding → GDN0/1/2 → attention3 前缀，分别在 baseline（DEFAULT）和 AVX2 两个独立 CPU 进程捕获数据，再做纯 bit 提取。checkpoint、framework、Torch/NumPy、源码、HTTP 字节范围和权重哈希都有固定准入；每次捕获形成新的来源记录。两次执行各含 cold/carried M128、Q8/K2，总计 5120 个 head 观察值；不宣称输入数值全都互异，也不保证不同 CPU 重建历史字节。

可选 `--historical-corpus` 仅回放本地保存且逐字节匹配原始 hash 的历史档案。新生成数据不会冒用 local/remote 历史名称或旧测试结果。下载权重、转换后 NPZ、原始 native 报告和完整 RTL trace 均保留在忽略目录；Git 只交付源码、固定来源和简短摘要。

整数精确算术和独立 C/fenv 实现校验逐节点值与 flags，实际 RTL 重新生成固定 HardFloat。native 比较继续按每个来源/phase/QK 分组，保持 max_abs≤0.03125、mean_abs≤0.005；结果不能被称为 native bit-exact。

## 修订交付的实际复验

- 新默认路径：两次官方执行产生 5120 个真实 head，另有 32 个合成 head。实际 RTL、整数和独立 C 对 5152×3132 个节点值/flags 一致；实际 RTL 中间 trace 和原始 gate 均通过。新 native 数据有 7 个 BF16 差异，最大绝对差 0.015625，八组全部通过原阈值。
- 两种新 CPU 路径的投影输入和 native 数组确实不同；摘要仍明确不把执行观察数称为唯一输入数。整个原始 BF16 producer audit 分别仍有 5/9 项失败，不能据此接受完整 block。
- 本地历史重放也重新跑了当前源码的全部实际 RTL：5120 个真实 head、32 个合成 head，通过；仍为 15 个 native 差异，历史 remote carried-K 最大差恰好 0.03125。历史结果和新生成结果分开记录。
- 每种完整回放均含 48 项拒绝、8 项 Q/K opaque gate/padding、四阶段 reset 恢复；真实 debug 核对 82432 个归约 chunk、5152 个 rsqrt、82432 个输出 chunk 和 5152 个最终 FP32 向量。RTL 不宣称逐一暴露所有内部树加法器；全部树节点由整数/C 独立比对。
- 旧默认与显式参数 0 对原始 core 的 64 事务逐周期等价通过。另一次独立实际 RTL 对抗测试通过 60 次完成、10 个 reset flush；独立旧版 miter 通过 64 事务 / 20573 周期。
- 修订后的相关回归：普通与 Python -O 各 669 项通过。全仓 2670 项通过、5 项失败，失败名称与 e9c2eae 的已有基线完全相同；没有把全仓描述为全绿。
- 消费方式修改后的实际 RoPE SharedL2 回放重新通过 163840 个唯一旋转 pair、5184 个事务。三个旧 RoPE 数组只从当前树移除，原缓存仍在。

简短证据：

- `reports/execution/U00_2_QK_NORM256_CANDIDATE_20261007/fresh_summary.json`
- `reports/execution/U00_2_QK_NORM256_CANDIDATE_20261007/historical_replay_summary.json`
- `reports/execution/REBUILDABLE_ARTIFACT_MIGRATION_20261007/result.json`

## 复现与剩余工作

完整安装和有界下载命令见 `.github/workflows/qk-norm256-candidate.yml`。取得固定层 0、层 3 和前缀 payload 后，运行：

```sh
python scripts/run_qk_norm256_candidate.py --output work/qk_norm256_candidate_result
bash scripts/review_qk_norm256_candidate.sh work/qk_norm256_independent_review
```

输出目录必须新建或为空。CI 在 clean checkout 上物化临时数据，实际执行新官方数据与 RTL 门禁，只发布允许字段的 `summary.json`。可选历史档案未提供时，四项历史专属 unit case 明确跳过；普通算术、来源拒绝、重新物化和新 native 实际 RTL 门禁不跳过。

下一有界门禁：让真实 Matrix 按明确顺序生产 Q/K，冻结 FP32→BF16 边界，再串接 Norm 与 RoPE 候选并保留 Q gate，验证实际内存及 owner 握手。当前只完成默认关闭的同输入组件/布局门禁。Matrix producer、Norm→RoPE 组合、SharedL2 / 全 tensor owner、Command128、三模型完整 block、PPA 和固定资源整 block useful-wall MAC≥90% 均继续 OPEN；U00.2 ongoing，U01 to do。
