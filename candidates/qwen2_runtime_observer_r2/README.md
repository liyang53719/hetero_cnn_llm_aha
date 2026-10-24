# 正常源码 Observation：真实 Attention M1/M2、十字段和无干扰核验

**PASS 仅限本包钉定 profile 的单 Attention 软件组件。** 两 arm 都启用同一个 ordered fold，只切换观察器 off/on；复用既有 combined Matrix/SiLU ELF、同一真实 owner/client/服务路径。不是全 block、M16/M128、RTL、频率或 80%/90% 利用率验收。默认 production/entry/Chisel 和旧 observer/source pins 全不改。

## 真实结果与边界

| 范围 | M1 | M2 |
|---|---:|---:|
| 输出 words | 1536 | 3072 |
| 因果 scores | 12 | 36 |
| 中间字段 | 10 | 10 |
| packed 最后消费 ACK / done | 12 / 12 | 24 / 24 |
| 父进程 wall 秒，仅运行记录 | 3.8302 | 5.3401 |

每个规模只运行一次，均 exit 0、无 timeout、子进程组已清空。每次 1 CPU、1 GiB、30 CPU 秒、45 wall 秒。启动前、两次之间、运行后全部 696 pins（含 qr/kr/v）流式核验；没有重新编译或下载权重。输入是已有 qr/kr/v 组件输入，不是完整 block 首端输入。

捕获 `dot_parts / unrounded_dot_sum / dot_bf16 / scores_bf16 / softmax_exp / softmax_fp32 / prob_bf16 / normalizer / pv_raw / pv_bf16`。只读捕获实际执行值，逐字段 words、presence、shape 与原独立 Python recipe 比较，不用参考补缺；数值逐字一致，不采用容差。参考在两个实际 owner terminal ACK 且 off/on 控制对比之后运行，保留原 AST 加载的独立控制和原精确 RNE helper。共享精确算术 primitive 明确披露，不声称另一套独立 FP 实现。

两 arm 的输出、scores、写地址/tag/内容、服务/Scalar/owner 计数、FMA 数、服务 edges、结果持有检查、ordered work/lane 事件及 owner clock 均精确相等。原生 reset 不重置 ticket counter，因此只对 ticket 做已验证完整生命周期、双射且不合并 live ticket 的首次出现重命名；raw 服务事件独立保留，其他字段/顺序不宽松化。**这是所测两例的无干扰证据，不是任意 M/异常路径的普遍证明。**

真实 postflight 完整库存为 270 entries / 267 objects、19 映射文件（17 ELF、2 locale）。native load 后、每 arm terminal 后、最终参考比较后均先存 raw module/maps，再独立汇总两个审计的全部差额；全部通过。私有路径、完整库存、tensor 与 raw maps 不上传，本包只提供脱敏投影和原文件哈希。

## 来源与历史失败不改写

- 所选模型源码沿用已发布 owner `a672a56feef9b661f6682bedfcbd702d1ddbc3fa` 的组装源；observer 主片 `c8de5739b68e7cfc3489cbe677681a5af6009442`，正常源码 binding `e8375f64d861c45fea3fbd6d445e5c213ff895a6`。独立 `REFERENCE_SOURCE_IDENTITIES.json` 固定十个参考角色。
- 最终 config SHA256：`793635db42c92f03ea022cafed313f49a40b6d6de05b33fb8baff60f33056030`。
- 数值准备独审 SHA256：`af8b1223825eb7f92c038ec1c9010508942302b4eb65f45fbff0499b652bfecc`。它只证明准备审查，实际运行另有明确授权和终态 receipts。
- 原第一次真实 M1 在十字段比较后因漏 pin `__future__.py` 整体 FAIL，M2 未跑；不追认中间阶段为整个 PASS。前序 cold 的 dataclass 定义工厂误判和 `_decimal` 显示名规则误判也保留 FAIL。
- 最终门按 spec/origin、精确 loader、canonical snapshot/live 对象和解释器 pin 验证 built-in/frozen，不要求 `__name__` 与 spec 字符串机械相等。namespace、typing 兼容对象、synthetic observer package 均单独精确登记；foreign/替换对象仍拒绝。

正常冷准入 14 个目标、247 entries / 244 objects、18 映射文件通过；允许已 pin Python/NumPy 正常初始化及自检、精确 source-bound dataclass 定义工厂（140 次），**不是“没有加载 ELF”**。cold 不构造服务或 Observation，不调用 Matrix CDLL/reset/job，不读用户 tensor。cold PASS 本身不等同于实际数值 PASS，后者仅由本次 M1/M2 receipts 支持。

## 文件与复现

`harness.py`、`runtime_observer.py`、`reference_capture.py` 实现真实 owner 驱动、被动服务事件和 terminal-only 原参考捕获；`worker.py / launch.py / admission.py` 保持一次性 ledger、exact review/config 启动门及资源限制。`module_inventory.py / cold_import.py / run_cold.py` 是身份/冷准入工具；`replay_inventory.py` 只重放钉定 JSON 元数据，不能代替 live 身份核验。

`PROFILE_PROJECTION.json` 是 696 pins 的脱敏相对路径投影，**不是可执行 config，不声称 git clone 后自包含运行**。实际数值复现必须具备完全相同的组装源、原参考源、现存匹配 ELF、Python/NumPy/system runtime/Git snapshot 及冻结 qr/kr/v；不得调用旧强制 compile_fresh 入口来“复现”。迁移路径会改变 config SHA，必须重新形成对应 profile 与 exact review，不能替换历史 pin 或复用旧一次账本。

可独立运行的 104 项纯软件测试，不加载任务 NumPy/native/DUT：

```sh
for t in test_preparation test_admission test_module_inventory test_cold_import_mock test_worker_audit_mock; do
  python3 -I -S -B candidates/qwen2_runtime_observer_r2/$t.py
done
```

另 21 项原参考源码静态/假帧测试需十角色 source roots。按 `REFERENCE_SOURCE_IDENTITIES.json` 的 root/relative/bytes/sha256 对应本地精确源码，生成本地 JSON：每角色为 `{ "path": "绝对规范源码路径", "bytes": N, "sha256": "固定hash" }`。只读取这些源码；不要提供 tensor 或参考输出替代源码。

```sh
python3 -I -S -B candidates/qwen2_runtime_observer_r2/test_reference_capture_static.py \
  --reference-pins LOCAL_REFERENCE_PINS.json
```

在所钉定 CPython 3.12 环境，全部 125 项分别以 normal、`-O`、`-I`、`-I -O`（均带 `-B -S`）通过。每脚本 1 CPU / 256 MiB / 20 CPU 秒 / 25 wall 秒；完整原日志与执行身份保持本地，公开摘要逐项列 hash。不自动发起 CI、native 或 elaboration。

实际准入顺序是 source/runtime 精确核验 → 一次冷准入 → exact 独审 → 明确授权 → `launch.py --m 1`；只有所有门和 cleanup 成功才能同 profile `--m 2`。参数包括本地 config、review、精确 review SHA 和全新 output。任何失败/未知保留并停止，不自动重试。公开脱敏投影不可直接传给 launcher。

## 尚未资格化

完整 block suffix/dispatch 接缝、新 fullgraph observer、M16/M128 同源执行、完整固定资源周期分母和利用率、Chisel 实际行为/RTL/时序均仍 TEMP。宿主时间、owner clock、model step 不冒充硬件周期；legacy PV 路径未因本片变成新实现。不能由本片宣称 80% 或 90%。

最终只读独审摘要见 [EXECUTION_REVIEW_SUMMARY.json](validation/EXECUTION_REVIEW_SUMMARY.json)。原终态审查 SHA256 为 `2a572aa0e44e010c32b77107775c6eb1f06302768e7b7cd6f7da398d34d4ffa5`：独核 696 pins、20 capture、8 完整 module/maps 阶段、4 份服务事件流和两个单次账本；M1 完整成功先于 M2，旧三次 FAIL 保持，无未解阻塞。该审查不授权更多执行。
