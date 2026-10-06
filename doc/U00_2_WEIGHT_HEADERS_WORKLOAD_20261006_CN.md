# U00.2：三模型真实权重 header 与 OPEN workload 证据

## 本轮结论

U00.2 已推进但仍为 ongoing。已实际读取三个固定 checkpoint 的全部 16 个 safetensors header，归档 321,392 字节、2,637 项 tensor；不是仅将名称与 index 对齐。没有下载或哈希权重 payload，没有执行官方 forward、实际生成 RTL 或 MAC 性能测试。U00、U01 和 90% 验收不关闭。

可复验入口：`config/workloads/three_model_m128_open.json`。每个模型绑定独立的 checkpoint revision、profile/config/forward 原字节和 header bundle；五个典型 block 保留 batch=1、M128。完整必需性能用例集合和真实回放依赖仍 OPEN。

## 固定来源与真实观察

| 模型 | Checkpoint revision | Header / tensor | 已核验主文本 shape | 典型层 |
|---|---|---|---|---|
| Qwen2-1.5B-Instruct | ba1cf1846d7df0a0591d6c00649f57e798519da8 | 1 / 338 | 338 | 0，B2_DENSE |
| Qwen3.5-0.8B | 2fc06364715b967f1860aea9cf38778875588b17 | 1 / 488 | 320 | 0 GDN+dense FFN；3 Attention+dense FFN |
| Qwen3.5-35B-A3B | 62704185bd97ad488cfc404e7caea797396b74dc | 14 / 1811 | 692 | 0 GDN+MoE；3 Attention+MoE |

- 保留 Qwen2 的 Instruct 身份。它实际是单文件 `model.safetensors`，官方 index URL 返回404；校验使用官方API单文件元数据，不制造 index。
- Qwen2 官方 Transformers v4.40.1 标签被解析为不可变 commit `9fe3f585bb4ea29f209dc705d269fbe292e1128f`，重新按 commit 获取的 modeling/configuration 字节与既有 SHA256 一致。
- 0.8B framework 仍固定 `14e738b5d0cc69aa27a95dde272aea41fde44f2f`；35B framework 保留 `42ca97014c85d71a88ad60d55f08cb9fb4d26e2c`，新增实际 modeling/modular 原文件。Checkpoint 与 framework revision 分开，不声称匹配训练时实现。
- 35B 保留 `62704185…`，不切换已经变化的可变 main。
- Qwen2 的338项均BF16。0.8B实际452项BF16、36项F32；35B实际1751项BF16、60项F32。
- 两个Qwen3.5的每个GDN层中，`A_log` 与 `norm.weight` 实际F32，`dt_bias` 实际BF16。该事实是存储类型证据，不能冒充逐producer计算精度已验收。
- 35B routed experts 实际 packed：`gate_up_proj [256,1024,2048]`、`down_proj [256,2048,512]`。完整主文本层0/3分别18/15项，包含shared expert与路由权重。
- 两个Qwen3.5的全部index名称、分片归属与header完全一致；完整1,350项主文本shape与固定profile/raw config几何一致。vision/MTP仅纳入全文件元数据一致性检查，不加入典型text block支持范围。

## 校验器与来源强度

`src/heteronpu/weight_header_contract.py` 离线校验独立固定的bundle SHA256、每个原文件的长度/哈希、profile与raw config对应、官方API revision/LFS size、HTTP206精确Content-Range及原header字节。每个tensor检查dtype、shape×itemsize、offset连续性、重叠/越界、完整文件payload范围及跨分片重复。JSON重复key、非有限常量、bool冒充整数、错误名称/分片/几何均被拒绝。

官方LFS的whole-file SHA256保留为 `advertised_lfs_sha256_unverified`。它是官方公布的全文摘要，不是本机对权重内容的哈希。HTTP ETag同样不被当作payload SHA256。原API回复作为时点快照保存，下载量等字段未来可变化；不要求新API响应保持全部字节相同。

`scripts/collect_weight_headers.py` 支持向新/空目录重新取header：先取8字节长度，再取受限header；服务器若忽略Range或返回错误范围，在读取body前拒绝。重跑不允许复用含旧PASS的目录，以免失败后遗留成功回执。本轮对0.8B通过正式CLI完成第二次在线取header，59,848字节SHA256再次一致；其余分片由本轮初始采集及完整离线验证覆盖。

## OPEN workload 与禁止升级

`src/heteronpu/workload_evidence.py` 只接受第一阶段metadata准备schema。它拒绝将任意hash字符串、合成数据或布尔PASS写入缺失回放字段，不存在靠填假摘要即可让门禁关闭的路径。

以下实际证据仍缺失：

- past-KV长度、官方上游M128输入、位置轴/attention mask、KV/GDN/conv初始状态及版本原字节
- 实际所需tensor payload、同源双参考全量结果、逐producer精度/舍入/比较器策略
- 真实35B路由histogram、实际固定资源tile映射及padding排除
- 冷暖cache与传输/复用条件、实际生成RTL/source/tool哈希
- 本次DUT固定Matrix MAC/cycle、Vector单元和MAC/非MAC计数单位
- 执行前固定的完整必需性能用例集合

已继承的M128与batch1不等于完整性能workload冻结。不擅自改变token、精度、初态、cache或MoE路由争取90%。Matrix主口径仍为 `useful_macs/(configured_macs_per_cycle*whole_block_wall_cycles)`，含descriptor、DMA、stall、阶段间隙、padding和drain；起点为launch接受，终点为全部最终输出与状态写ACK。Matrix与Vector分报，最低90%不变。

## 回归与证据

正式命令、退出码、源哈希及日志归档在 `reports/execution/U00_2_WEIGHT_HEADERS_20261006/`。本轮新增129项测试，覆盖实际原始header、输入污染、假完成、固定M128、整数/JSON/shape边界和HTTP读取上限；普通及 `python -O` 均运行。精确最终统计见 `result.json`。

已建立独立只读CI `weight-workload-evidence`，直接测试该commit的归档原字节和OPEN门禁；不依赖外网模型下载。`--require-complete` 必须退出2并报告U00.2 OPEN，CI明确验证这一点。验收中的5项既有全仓失败保留，不能把focused通过写成全仓通过。

复验命令：

```sh
PYTHONPATH=src python scripts/validate_workload_evidence.py --output work/weight_workload_evidence.json
PYTHONPATH=src python scripts/validate_workload_evidence.py --require-complete  # expected exit 2
PYTHONPATH=src python -m pytest -q tests/test_weight_workload_evidence.py
PYTHONPATH=src python -O -m pytest -q tests/test_weight_workload_evidence.py
```

本次独立复核发现并修复了profile未全量绑定与旧采集输出遗留PASS两处问题。当前只发布可复验的metadata准备能力；下一步应按本清单逐项取得真实payload、官方输入/初态及双参考，之后才能冻结实际workload并接入数值RTL。
