# 冷 KV 比较对象纠错候选（未接线）

## done / ongoing / todo
- done：纯身份/复制检查函数及 13 项合成冷测；未执行 DUT、官方模型或 CI。
- ongoing：独立审查及新 sibling 的正式比较适配。
- todo：另行批准接入 fresh 完整同链；本目录不能授权运行、冻结参考或升级历史结果。

## 规范与旧门

`spec/numerical_contract.md:47` 要求 BF16 存储读回逐 bit 等于 BF16-rounded append value。
原 `qwen2_live_attention_model_m128/compare.py:30–34,63` 额外要求 DUT KV 与官方 KV 逐 bit 相等；原 `qwen2_live_fullblock_model_m128/compare.py:36–44` 又要求 DUT k/v 与官方 cold cache alias 逐 bit 相等。两处旧源码及旧 FAIL 全部保留。

候选仅检查同 run、同 live identity 的最终物理 cache 严格等于 DUT k+v，不返回数值 passed 或指标。正式比较器必须复用原 `native.compare` 和 `native.stage_verdict` 对 k/v 以及最终 cache 两个 subspan 执行原 operator 门：max_abs <= 0.03125 且 mean_abs <= 0.005；其余原节点及 block 门不变。

独审发现早期候选 math.fsum 与原 np.mean(float64 abs error) 在阈值边界可产生不同 verdict；已删除候选全部数值归约。回归用合法 BF16 合成误差证明原 max=0.03125、mean=0.005000000000000001 时必须 FAIL。±0 位差异计数亦由原 uint32 比较实现负责，不能用 float != 替代。

## 固定接口与来源要求

`compare(...)` 无文件读写、无默认动作，仅接受显式 bytes 和元数据。
- DUT k/v：token-major，128 token、2 head、128 dim，各 131072 字节；cache 为 k 后接 v，共 262144 字节。
- 官方 k：原 head-major `[1,2,128,128]`，唯一显式转换为 token-major。
- 官方 v：原 projection token-major `[1,128,256]`，不得再次转置。接口不接官方 cache_k/cache_v。
- 每项 DUT receipt 必须提供精确 role/run/live_identity/layout/bytes/sha256/sealed/terminal/ack_bytes/ack_64b_beats/origin。调用方另传已准入 run/live identity 与三项产物摘要承诺。
- cache 必须来自最终 sealed `actual['kv']` 的物理读回，origin=`SEALED_ACTUAL_KV_PHYSICAL_READBACK`；摘要来自最终 `sealed_actual_outputs['kv']`。禁止调用方现场拼接 k+v 冒称读回。k/v origin=`SEALED_ACTUAL_PRODUCER`。
- cache 完整 ACK 262144 字节/4096 beat，k/v 各 131072 字节/2048 beat。字段一致性不能替代真实 pc9 地址、extent、ACK 覆盖、同链身份和终态验证。
- official_commitments 来自另行审定的新官方契约；不能现场从未验证输入计算后冒称独立承诺。

返回 same_live_exact_copy、如实的 official_kv_exact_copy 跨官方诊断，以及 numerical_acceptance_claimed/whole_block_acceptance_claimed/historical_run_upgraded=False。旧官方逐 bit 诊断可为 false，不改成 true。返回成功只证明所给证据的身份/复制一致性，数值可能仍 FAIL。

纯函数不能认证自造 receipt 或摘要。真实接线必须从已验证的同 run 完成产物提取参数，保留原 source/runtime、地址、覆盖、重复 ACK、终态与债务门。零值或对称数组不能证明布局，所以固定转换与受信任 layout receipt 均不可省略。

## 冷测

从仓库根目录执行：

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/work/runtime_recovery/site-packages:$PWD" OPENBLAS_NUM_THREADS=1 python3 -m unittest candidates.qwen2_cold_cache_contract_candidate.test_compare -v
```

13 测试仅合成数据。覆盖 exact、容差内官方不同（正式判定调用原门）、cache 单 bit 容差内损坏仍拒、截断、错布局、未 ACK/未 seal/未终态、身份/摘要不符、非有限及非 BF16；另直接调用原比较器测试 max/mean 越门、边界回归及 ±0 位计数。数值越门不会由纯 helper 判定，必须由接线原数值门拒绝。
