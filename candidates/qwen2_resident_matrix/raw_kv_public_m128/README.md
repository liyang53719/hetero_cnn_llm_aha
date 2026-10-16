# 独立 M128 fresh profile：来源与前置条件准备

## 中文计划

- 已完成：真实 M16 Public21 链的安全 PASS 已冻结在 `raw_kv_public_run/M16_EVIDENCE.json`；27 个 assigned observed gates、28 个 observed fields，完整 29 节点验收仍为 false。
- 已完成准备检查：独立 M128 资产验证、来源兼容映射、入口授权分支及 24 个普通 / -O 冷测试。本目录不会改写已执行的 M16 profiles、来源 pins 或旧失败记录。
- 待完成：setup128 变体、双凭据准入、监督运行器及独立工作流审查；真实 128 行 arena、两个参考和原生模型 gate 必须重新生成。
- 本批状态：`PREPARATION_ONLY`。运行授权和资产运行时来源准入均因尚缺 setup 变体而拒绝；没有 M128 数值执行、下载或原生调用。

## 精确继承与显式差异

M16 安全凭据只作为已验证前置结果和来源身份，不可代替丢失的私有输入、参考或 ELF。新运行必须重新验证它们。M128 兼容性保留原始 owner、算术、原生生产器、raw KV 传输及观察器的精确字节；只允许独立 pins 明确列出的 assets/setup/ReducedPublicExecution 入口变体。七个旧组合输出完全不变。

第一批在原有八个组合输出上替换一个入口、增加 assets 变体，共九个输出。以后增加 setup 变体才构成十个最终输出。不能把当前九个输出当成可运行的完整 setup。`profile` 必须先验证冻结合同，不能信任调用方任意提供的 replacement 哈希。

执行目标仍为原始 PV16 Attention 调度和完整 Public21 软件链，128 是输入行数。默认 M16 和原始入口的 900/1800 秒限制不变；新增预算路径必须同时满足明确的新 profile、canonical rows128/past0/raw=true、成功 M16 凭据和完整来源兼容检查。

## 原生前置条件和布局

原始 `qwen2_layer0_model_gate.run_gate(tokens=128)` 要求 authentic native M16 small_gate。新的 setup 必须在相同新下载 payload 上先生成 native M16，再在独立进程生成 native M128；原始校验器检查 payload、runtime、输出和语义。历史完整链 M16 的安全摘要不能冒充该 small_gate。

新 M128 Q/K 导出保持原始生产器的 token-major 布局，不使用历史归档 M128 的 head-major 特例。128 行 input/arena 的身份、全部导出形状和实际字节必须重新校验；不会复用 M16 张量哈希作为 M128 输出。

## 独立预算提案（尚未执行）

新 profile 计划使用 setup 900 秒、数值工作 2400 秒、外部数值阶段 2430 秒、总包装器 3420 秒、job 60 分钟，单次尝试并保留清理/提交余量。历史完整链约1548秒，加独立 Attention 已测 loan 增量约498秒，粗略约2046秒；2400秒只有约17%的余量，不保证完成。设置预算包含新的 native16 前置 gate 与 native128，不能把它们移到预算外。

此前 M16 PASS、独立 Attention M128 PASS 均不构成本目录完整链 M128 PASS。不得据软件墙钟、事件数或有效 FMA 比例宣称硬件利用率。

## 重现冷测试

```sh
python -m unittest candidates.qwen2_resident_matrix.raw_kv_public_m128.test_profile candidates.qwen2_resident_matrix.raw_kv_public_m128.test_assets128 -q
python -O -m unittest candidates.qwen2_resident_matrix.raw_kv_public_m128.test_profile candidates.qwen2_resident_matrix.raw_kv_public_m128.test_assets128 -q
```

冻结合同覆盖 201 个来源输入，计入 pins 本身为 202 个；零 fuzz 组合严格产生九个输出。测试仅执行短暂本地源码 patch 和 metadata fixtures，无模型包、原生库或数值生产器。
