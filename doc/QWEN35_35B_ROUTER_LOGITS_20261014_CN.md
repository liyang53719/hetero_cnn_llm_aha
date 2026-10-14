# Qwen3.5-35B-A3B L0 router logits：固定输入的实际 Matrix 重放

## 本次交付边界

本候选验证原始 H2048、N256、top-8 router 的 **logits 部分**。输入是此前实际 post-attention norm 已发布、已保存且有 SHA256 证明的 BF16[M,2048] 字节；M=16、128。候选把这些输入作为只读区域加入新的 TypedMemory，使用现有 Matrix、Vector16 和 LargeKProjectionOwner，产生全部 M×256 个 BF16 logits。

这不是同次调用内的 postnorm→router 活跃生产者交接；不包含候选 softmax、top-k、归一化分数或索引发布 owner，也没有完整 router/block、公开 command128、RTL、频率、吞吐或硬件周期验收。`owner.json` 的轨迹与主机用时均为软件观察。

基线为 `8e0b2bbd35b3fee5ba2ca3e1f37e9274266b7689`。`logits_identity.json` 固定所用基线依赖、候选代码、原始模型配置和完整 router 类、输入生产者摘要、权重 manifest/字节、运行时、Matrix/Vector 二进制、C 编译器及 libm 身份。后续 Git 提交无需保持相同 HEAD，但这些所用文件的字节必须仍与身份表一致；没有跳过身份检查的开关。身份文件自身的初始 path/bytes/SHA256 在解析后及执行终态被再次核对，不能通过中途改写身份表重新授权源文件变化。最终封存执行时的 checkout HEAD 独立记录为 `36dd2c473815a931e1f74463e9d43e538c11f2f6`，不把它混写为依赖基线。

## 冷检查

从仓库根目录执行，默认不导入 NumPy/Torch、不访问权重或 runtime，不执行 numerical owner：

```bash
python -S -m candidates.qwen35_35b_router.run_logits
python -O -S -m candidates.qwen35_35b_router.run_logits
PYTHONPATH=src python -m unittest \
  candidates.qwen35_35b_router.test_payload \
  candidates.qwen35_35b_router.test_reference \
  candidates.qwen35_35b_router.test_logits -v
PYTHONPATH=src python -O -m unittest \
  candidates.qwen35_35b_router.test_payload \
  candidates.qwen35_35b_router.test_reference \
  candidates.qwen35_35b_router.test_logits -v
```

默认输出的 `actual_status` 必须是 `NOT_EXECUTED`；`PASS_COLD_SOURCE_IDENTITY_ONLY` 只代表冷源码身份检查。测试覆盖缺失显式参数、未 opt-in 的 fixture、源文件漂移、输出目录错误/重复、生产者与输入漂移、权重 manifest/native/runtime/编译器哈希漂移，以及全量 logits 两个比较端任意末元素变化、非有限值和形状错误。所有拒绝使用显式异常，在 `python -O` 下仍生效。单元测试中的 BF16 零值比较不是实际模型数值验收。

## 显式实际重放

所需 fixture 不进入 Git，也不会自动下载或通过历史 PASS 代替运行。当前已恢复环境的复现命令为：

```bash
work/runtime_recovery/python.sh -m candidates.qwen35_35b_router.run_logits \
  --run-actual \
  --producer-m16 work/reuse_owner_actual_m16 \
  --producer-m128 work/reuse_owner_actual_m128 \
  --payload work/qwen35_35b_router_payload_20261014T0657Z \
  --runtime-root work/runtime_recovery \
  --matrix-library work/recovery_matrix_library/matrix_silu_numeric.so \
  --matrix-receipt work/recovery_matrix_library/compile.json \
  --vector-library work/recovery_vector/gdn_vector16.so \
  --out work/router_logits_fresh
```

输出目录必须是新建的 ignored `work/` 子目录。运行必须处于已固定的一核 DEFAULT CPU、单线程 Torch 2.10.0+cpu / NumPy 2.3.5 runtime 内；`python.sh`、runtime receipt、相关二进制和 Python 身份均被核对。运行时完整依赖源码闭包没有被证明。

路径参数均显式提供。原生产者 `summary.json` 可保持原字节迁移到新目录，读取的文件名固定为 `post_attention_norm.actual.bf16le`，重新核对完整字节数及 SHA256。Matrix/Vector 的原生 build receipt 本身带路径；换 checkout 后须用既有构建工具生成相应当前路径的有效 receipt，并仍匹配固定源码、编译器和二进制身份，不能编辑旧 receipt 假装重建。固定 runtime 的解释器路径/二进制依赖也必须可用，因此这不是任意 Python 或任意主机可执行的通用运行时包。

每次显式执行会重新运行完整未改动的 upstream router 类，并重新编译、执行独立 C 诊断；随后新建实际 typed owner 运行 M16/M128。实际执行函数只接收输入/权重、资源和身份表，不接收任何预期输出。只有成功终态、真实写回发布和资源排空之后，才读取 fresh 官方/C 输出作比较。完整输出、owner trace、动态库、反汇编及诊断数组始终保存在 ignored `work/`。

## 验收与保留的失败诊断

- 独立 C 和实际 owner 均采用两段 K1024、段内 pair-high-first、FP32 部分和合并后 BF16 RNE；这只是本固定运行时的诊断 profile，不是官方模型/硬件 profile 准入。
- M16：全部 4096 logits 对 fresh 官方/C 输出 bit-exact，8192 字节写入和 ACK。
- M128：全部 32768 logits 对 fresh 官方/C 输出 bit-exact，65536 字节写入和 ACK。
- 同一资源身份保持，输入/权重不变，输出写覆盖及 ACK 覆盖完整，Matrix/Vector/owner/shared-memory 均排空。
- 原始 ascending sequential-K2048 C recipe **仍不通过 bit-exact**：M16 为 1 个、M128 为 4 个 logits 不同，最大 1 BF16 ULP、绝对差 0.03125。不得用阈值放宽把它改写成 PASS。

最终源代码对应的测试/实际执行、精确 artifact SHA256 和完整字节数见 `reports/execution/QWEN35_35B_ROUTER_LOGITS_20261014.json`。其中只保存元数据、计数和哈希，不保存 logits、权重、路由 ID/分数数组。

## 仍开放的下一道门

原精度研究 `work/router_precision_20261014T0702Z/SUMMARY.json` 保持原样，SHA256 为 `319e232b758aed39bc4dfe5f3bd4a5c0f4f88293ad6a51e60a75b2d2c16a6826`。历史 host-only tail 诊断观察到 M16/M128 的 rank-8/9 tie 行数为 0/41；这里只保留计数和原始证据哈希，没有把该诊断作为新 owner PASS，也未复制其 ID 数组。

真正 router 链仍需：同次 TypedMemory 调用内已发布 postnorm 的活跃交接；固定 FP32 softmax 计算与归约；明确 top-8 相等值/排序语义；选中 8 值的 FP32 求和与除法；有界 score/index 状态及原子发布。此次未实现这些 tail 算法，也没有修改生产 Scala。发布批同步中文计划/ledger，并新增独立冷 CI：15+15拒绝门及默认NOT_EXECUTED报告；其paths覆盖全部100个固定基线依赖和router候选。CI不执行外部实际模型重放，不启动昂贵Host任务。
