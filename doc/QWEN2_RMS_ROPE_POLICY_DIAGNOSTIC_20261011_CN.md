# Qwen2 L0 RMS1536 与 FP32 RoPE 表的有界软件诊断

**状态保持 `DIAGNOSTIC_NOT_ACCEPTED`。** 本项单算子诊断只重用既有 cold/carried M16、M128 捕获，执行 RMS 单算子及位置 0..255 的 RoPE 表生成，没有重跑完整 block、attention、QKV/dense、RTL 或模型质量评测，没有下载权重、改 v0 数值规范或改任何既有 candidate。

候选的归约顺序与 host 表生成不是 v0 硬件配方，仍不符合现有 v0 硬件准入；软件同输入对齐没有改变这个边界。

新的显式软件 RMS 配方在全部 20 组、1440 行评估中，与官方**相同输入**的 8 个 FP32/物化观察节点及最终 BF16 输出逐位相同。1440 是包含重复 token、actual/official 不同残差输入和两个 cache 条件的行评估总数，不是 1440 个独立 token。每行都完整检查 1536 个 channel，没有只挑最坏 lane。

独立普通 C 对全部 10 个候选节点逐位相同；对全部 1440 行的 mean division、sqrt、reciprocal，另以精确整数有理数的相邻 FP32 中点不等式验证 RNE。没有把 `torch.sqrt` 当成官方 RMS 中不存在的独立输出节点，也没有把两步 sqrt/reciprocal 称为数学 rsqrt 的单次正确舍入。

## 实际 backend 与 source pin

官方实现仍是 Transformers 4.40.1、固定 Qwen2 源码及原模型 revision。Torch 是 2.10.0+cpu，commit `449b1768410104d3ed79d3bcfe4ba1d65c7f22c0`；诊断固定 CPU 4 threads、interop 1、deterministic algorithms。运行时整体 capability 为 AVX512，**具体算子的 dispatch 另行确认**：

- sum、rsqrt、sin、cos、div_true 的 AVX512 指针为 null，实际回落到 AVX2。独立读取 8 个 stub × 3 个 capability 的 24 个导出符号，全部符合源码。
- sum 使用 V8；不是依据机器的 AVX512 标签选 V16，也没有复用现有 GDN1024 的 power-of-two / `1+gamma` 规则。
- rsqrt 的 AVX2 路径使用 FP32 sqrt 指令后再做 FP32 division，没有近似 rsqrt 指令。
- RoPE 的 pow_tensor_tensor 支持 AVX512，64 个 exponent 在本机由 `Sleef_powf16_u10` 处理。
- 此 build 的 FP32 sin/cos 通过 MKL 2024.2 VML 的 `vmsSin` / `vmsCos`，模式为 `VML_HA | VML_FTZDAZ_OFF | VML_ERRMODE_IGNORE`；不是 SLEEF sin/cos。

全部 14 个 Torch 源文件已按上述 commit 保存并逐字节固定，5 个相关 header 的主体与安装版本一致（安装版额外包裹 stability guard）。主要位置：

- [SumKernel.cpp:345](https://github.com/pytorch/pytorch/blob/449b1768410104d3ed79d3bcfe4ba1d65c7f22c0/aten/src/ATen/native/cpu/SumKernel.cpp#L345)：分层归约、ILP4、最后 lane 顺序求和；注册见 644 行。
- [ReduceOps.cpp:1414](https://github.com/pytorch/pytorch/blob/449b1768410104d3ed79d3bcfe4ba1d65c7f22c0/aten/src/ATen/native/ReduceOps.cpp#L1414)：CPU mean 使用 `sum_out(...).div_(dim_prod)`。
- [UnaryOpsKernel.cpp:529](https://github.com/pytorch/pytorch/blob/449b1768410104d3ed79d3bcfe4ba1d65c7f22c0/aten/src/ATen/native/cpu/UnaryOpsKernel.cpp#L529)、[vec256_float.h:476](https://github.com/pytorch/pytorch/blob/449b1768410104d3ed79d3bcfe4ba1d65c7f22c0/aten/src/ATen/cpu/vec/vec256/vec256_float.h#L476)：rsqrt 的 scalar/vector 算术。
- [vml.h:108](https://github.com/pytorch/pytorch/blob/449b1768410104d3ed79d3bcfe4ba1d65c7f22c0/aten/src/ATen/cpu/vml.h#L108)：MKL 高精度 sin/cos；[DispatchStub.cpp:309](https://github.com/pytorch/pytorch/blob/449b1768410104d3ed79d3bcfe4ba1d65c7f22c0/aten/src/ATen/native/DispatchStub.cpp#L309)：AVX512 null 回落。

## RMS1536 候选配方

每个以下节点单独舍入到 FP32，不融合算术：

1. 对 BF16 解码后的 x 逐 channel 计算 x×x。
2. 对 block b=0..2、residue k=0..3、lane l=0..7，按 t=0..15 顺序累加 index `512b + 32t + 8k + l` 的 16 项。
3. 同一 k/l 的三个 block sum 顺序相加；再按 k=0..3 合并；最后按 l=0..7 顺序累加。
4. 总和**除以 FP32 1536**，加 FP32 epsilon 1e-6，FP32 sqrt，再 FP32 1/root。
5. x×inverse 后 BF16 RNE；乘原 BF16 **direct gamma** 后再 BF16 RNE。

第 4 步不能替换成乘已舍入的 FP32(1/1536)。仅 carried M128 inputNorm 的 128 行里，这种替换会使 40 行的 FP32 mean 不同。现有 v0/legacy 的逐项顺序求和和 reciprocal multiplication 均原样保留，只在新脚本中作为对照重新解释。

对原 actual 输入的同输入比较：

| 输入组 / 算子 | 原配方不同 BF16 元素 | 原 max_abs | 新配方不同元素 |
|---|---:|---:|---:|
| cold M16 / input、post | 0 / 0 | 0 / 0 | 0 / 0 |
| cold M128 / input、post | 0 / 47 | 0 / 0.00390625 | 0 / 0 |
| carried M16 / input、post | 0 / 0 | 0 / 0 | 0 / 0 |
| carried M128 / input、post | 35 / 38 | 0.0078125 / 0.0078125 | 0 / 0 |

另外，在所有保存的官方原始输入上执行官方 RMS，均逐位复现其原捕获；在所有 actual 输入上执行 legacy 方程，也均逐位复现 actual n0/n1。候选输出没有注入任何原 block。

**同输入精确不代表原整链差异消失。** 只读对照显示 carried M128 新 RMS 作用于旧 actual r 后，与原官方 n1 仍有 13245 个元素不同，max_abs 仍为 0.12353515625（原 actual n1 为 13270 个不同）。cold M128 n1 为 701→654 个不同，max_abs 仍为 0.0078125。上游 residual 输入已不同；完整链改善尚未测量。

## RoPE 全位置表审计

独立普通 C 生成 exponent、`powf(1e6, exponent)`、FP32 reciprocal、FP32 position×inverse，再 `cosf` / `sinf`，最后 BF16 RNE。覆盖全部位置 0..255、64 个 distinct frequency，并复制为 Qwen2 split-half 的 128 维表。

| 表 | 新候选 BF16 不同元素 / 32768 | 原 double-libm BF16 不同元素 | 新候选 FP32 不同元素 |
|---|---:|---:|---:|
| cos | 0 | 12 | 2004 |
| sin | 0 | 10 | 1178 |

新候选与官方的 FP32 表 max_abs 均为 5.960464477539063e-8。glibc powf 与官方 SLEEF pow 在 frequency 37 的 power/inverse 各有一个 FP32 差异，导致 225 个 FP32 angle 不同。这些差异在本批 BF16 表上全部消失，**没有据此声称 FP32 表逐位等价、任意位置都等价或跨 host/libm 等价**。

所有 cold/carried 的原表捕获也全部被分别复现：actual 由原 double-libm recipe 控制，官方由固定源 FP32 cache→BF16 控制。原先 position145/frequency3 的 sin 边界包含在全表检查中。

保存了新候选和官方各自的完整 FP32、BF16 解码表及 SHA。后续若要跨机器固定 BF16 输入，可以把已核验表作为独立、版本化的外部常量产物；本批没有把这个选择写入政策或硬件。

## 运行与证据

入口：`scripts/qwen2_rms_rope_policy_diagnostic.py`。完成后仍返回 exit 1，不能用作硬件验收命令。

```sh
OPENBLAS_NUM_THREADS=4 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 \
work/recovery_20261011/python/bin/python \
  scripts/qwen2_rms_rope_policy_diagnostic.py \
  --source-evidence work/qwen2_rms_rope_sources_20261011 \
  --out work/qwen2_rms_rope_policy_diagnostic_20261011
```

已有目录拒绝覆盖；重现需要选择另一个新的 ignored work 输出目录。主诊断单算子段墙钟约 0.494 秒，不包含构建、输入校验，不能推导硬件周期或吞吐。

- 11 个 focused tests 通过：BF16 ties-even、direct gamma 与 pre-gamma rounding、1536 归约/除法、独立 C 每节点、整数 RNE 检查拒绝 1ulp sqrt 破坏、geometry/BF16/nonfinite 拒绝、证据 hash/alias 拒绝、signed zero。
- `work/qwen2_rms_rope_policy_diagnostic_20261011/RESULT.json`：主报告、每组全量统计及产物 hash。
- 同目录 `FROZEN.json`：输入、源码、runtime、编译命令和原数值门限。
- 同目录 `ORIGINAL_CHAIN_CONTEXT.json`：只读旧链对照，未重新执行算子。
- 同目录 `TEST_RECEIPT.json` / `BACKEND_VERIFIED.json`：小测试及 24 个 dispatch 指针的独立核验。
- `work/qwen2_rms_rope_sources_20261011/source_manifest.json`：14 个上游固定 source URL/SHA；`backend_observation.json` 保存精确符号及 installed-header 对照。

| 产物 | SHA256 |
|---|---|
| 诊断源码 | `9117f240243357786bd538908343fcfb3a791769f2061d585524594b96b76ef6` |
| 测试源码 | `b2a6766d85adc4df422f2b4319de0ceb9e95613f8357c8c1053cfa4f9b5027a2` |
| RESULT | `060bbb4e55fa0abba8ee7f253c68297630b90b2db778dec7dbceafc701e0eae5` |
| FROZEN | `500c4a52e8572bdcf9c295483dab5b533bae4a940ef9bc2df06f3ab216dd50c1` |
| 上游 source manifest | `52555a6d4b7b307e7e87bb2cb6bfcaf4b20d27fa58046ef50ea78427a38dcbf9` |

最小下一步是决定是否将这两个配方引入一个新的、隔离的软件 candidate，再做有界 cold→carried M16 控制和 M128 整链比较。当前不能撤销原 15 节点失败，不能认定硬件/RNE/precision 政策通过，也没有扩展到其他层或 Qwen3.5。

## 证据保全与复现边界

纯摘要、输入/输出哈希以及上游源码清单位于
`reports/execution/QWEN2_RMS_ROPE_POLICY_20261011/`。这里不包含输入/输出数组、
模型权重或可执行文件。14 个 Torch 源码 URL 固定到 commit，逐个核验字节数和
SHA256；`source_manifest.json` 保留原始字节，不能重新格式化后沿用旧 SHA。

历史 `backend_observation.json` 是附加的只读核查回执，不是原数值 CLI 的强制
输入。其 24 个 dispatch pointer 和 5 个 installed header body 已独立核验。
原 CLI 中的 backend 描述字段不构成运行时 dispatch 校验，后续重新运行必须
单独执行 backend 检查；CPU 型号或 capability 名称本身不足以证明具体 kernel。

原 `INPUT_GROUPS`、`ORIGINAL_CHAIN_CONTEXT`、`BACKEND_VERIFIED` 和
`TEST_RECEIPT` 是对既有文件的附加核验摘要，不能称为主 CLI 自动生成的产物。
完整重放仍需按哈希恢复原 sealed captures、gamma 和固定运行时。历史 cold
回执带有当时 checkout 的绝对 `native_directory`；仅有 Git 中摘要的新 checkout
不能直接执行全部原案例。应核验原文件后显式映射捕获根路径，不能编辑封存回执
或将新生成输入冒充旧刺激。本文的独立审查不授予硬件数值或跨主机等价验收。

新增 `scripts/qwen2_rms_backend_evidence.py` 提供上述独立来源检查。`restore`
按固定 manifest 恢复14份源码，`verify` 完全离线；输出当前24个pointer的存在/
空值布尔、5份header body、线程和CPU状态，以及实际 `libtorch_cpu.so` 的字节数
和分块 SHA256，不输出指针地址。两者都拒绝已有输出、路径穿越、symlink或
字节漂移。这不补齐旧capture路径映射，也不改变原数值CLI及其历史身份。

```sh
python scripts/qwen2_rms_backend_evidence.py verify \
  --sources work/qwen2_rms_rope_sources_20261011 \
  --report work/qwen2_rms_backend_new.json
```

11项纯mock测试通过，当前主机离线核验14/24/5项均匹配。新回执记录的
threads=4、interop=9、deterministic=false是该独立检查进程当时状态，不能
替代完整数值运行的4/1线程和确定性设置。原历史观察与新回执分别保留。
