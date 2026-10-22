# Fixed93 PV-reuse v2 离线证据容器检查入口

这是一个只读、失败关闭的完整 block **证据检查入口**，不是模型、数值参考或全 block 验收器。本候选仅检查外部可信终态声明与冻结 receipts 的一致性，以及两条 LEC1 文件的身份、帧结构、hash chain、真实 EOF 和终态 seal。

成功状态是 `PASS_REPORTED_TERMINAL_AND_TWO_STREAM_CONTAINERS_ONLY`。它同时显式返回：`fullblock_acceptance=false`、`numerical_acceptance=false`、`RTL=false`。不能把这个状态改述为 M128、调度/cache 对应或算法数组通过。

## 文件与运行

- `verify_evidence.py`：只读 CLI 和可调用的 `verify` 接口。
- `test_verify_evidence.py`：纯合成文件、手写 wire fixture 和拒绝测试。
- `r3/format.py`、`r3/decoder.py`：原 r3 codec 的逐字副本，没有 Writer、DUT、NumPy、ctypes 或旧审计脚本。

测试命令：

```sh
timeout -s KILL 15s python3 -I -S -B test_verify_evidence.py
```

测试进程设置单 CPU、15 秒 CPU/wall、256 MiB 地址空间。外层 timeout 也限定 15 秒；所有临时合成文件都在本 consumer 目录下创建及回收。合成测试临时文件由 `TemporaryDirectory` 回收；不读取真实运行、输入、权重或 reference。审计 hook 拒绝 subprocess、ctypes 动态库加载、shell 命令及 socket connect。这里的“无 native”仅指未运行 DUT/加速库，不是否认标准 Python/hashlib/zlib 的底层实现。

真实离线扫描需要另行审定的有限资源范围和已经冻结的证据。默认没有 `--scan` 必须拒绝，示意命令为：

```sh
python3 -I -S -B verify_evidence.py --scan \
  --run-root /path/to/frozen-run \
  --plan /path/to/approved-plan.json --plan-sha256 EXPECTED_SHA256 \
  --terminal-attestation /path/to/reviewed-terminal.json \
  --budget /path/to/frozen-budget.json --seconds 30
```

CLI 单 CPU、256 MiB 地址空间，CPU/wall 默认 30 秒，参数范围 1..3600 秒。时间上限不是完成时间保证；实际多 GB 扫描尚未测量。库接口检查单调时钟，但没有替调用方安装 OS 资源/信号限制，调用方负责外层约束。程序只向 stdout 输出一个最终 JSON，不创建结果文件，不提供覆写任何证据的 API。不得由 shell 把 stdout 重定向覆盖原输入。

## 信任边界和计划格式

`--plan-sha256` 必须通过独立可信渠道给出，不能在未检查来源时临时计算并当成批准。计划和 terminal attestation 都不是本程序生成。它们也不是数字签名；有能力重写计划并替换可信 SHA 的主体可以改变声明。

独立审查者必须先从**原执行会话**建立 launcher 自然退出 0、精确进程身份和清理证据，再生成终态 attestation。单独出现 LAUNCH 的 PASS 文本不够，因为 launcher 写 PASS 后还会检查终态。会话消失、预算到期、停止写文件、零 stderr 都不能替代这个前置条件。

计划 schema 为 `fixed93-pv-reuse-offline-container-plan-v1`，顶层键必须恰为：

- `identity`：`source_manifest_sha256`、`admission_sha256`、`budget_sha256`、`source_map_sha256`、`reviewed_source_manifest`（必须是同一 manifest-file 的 SHA，不是路径）。
- `invocation`：精确原 `argv` 和 `cwd`。
- `receipts`：以下七个角色，各 `{bytes, sha256}`。
- `streams`：`wholeblock` 和 `attention`，各 `{bytes, sha256, limits}`。
- `terminal_attestation` 和 `budget`：各 `{bytes, sha256}`，对应单独传入的文件。
- `schema`。
- `evidence_contract`：必须精确为 `original-algorithm-arrays-plus-true-events-and-pv-reuse-attention-v1`，并与 `RESULT.evidence_contract` 和 `RESULT.wholeblock_observation.evidence_contract` 相同；不接受旧合同或所有副本一起漂移。

固定 receipt 相对路径：

| 角色 | 相对 run-root 路径 |
|---|---|
| launch | LAUNCH.json |
| native | supervisor/native.json |
| lease | LEASE.json |
| consumed | CONSUMED.json |
| result | run01/RESULT.json |
| algorithm | run01/ALGORITHM_ARTIFACT_SEAL.json |
| attention | run01/attention_observation/summary.json |

固定流路径是 `run01/wholeblock_events.lec1` 和 `run01/attention_observation/attention-events.lec1`。不接受自选目录、`..`、符号链接或硬链接。计划/终态/预算最多 128 KiB，每份 receipt 最多 8 MiB；JSON 深度、节点数、重复键和非有限数另有检查。字段用于计数/标识时拒绝 bool 冒充 int。

终态 attestation schema 为 `fixed93-original-session-terminal-v1`，键必须恰为 `schema, original_session_id, launcher_exit_code, cleanup_confirmed, ownership_uncertain, run_root, parent, child, identity`。原 session ID、parent/child 的 PID 和 start_ticks 必须是正整数。该 attestation 是外部可信原会话核验的声明，本工具只检查一致性，**不独立观察或重建进程死亡**。

计划中的 `limits` 必须逐项等于已 pin 的 budget：wholeblock 取 `wholeblock_trace_limits.codec`，Attention 取 `attention_trace_limits.codec_limits`。r3 文件 header 不得扩大该 policy；不得依当前流大小临时放宽预算。

## 实际完成的检查

1. 在打开两条流之前，核七份 metadata 的 size/hash、终态状态与 scope、预算及独立 attestation；检查 LAUNCH/LEASE/CONSUMED 的身份和 output 路径、原 native argv/cwd、natural-exit0/WNOWAIT/reap/group-absent/cleanup 声明。
2. 合法自然退出后的 anchored `kill_attempted=true` 不被误拒；检查 group-before-reap、kill 结果与 diagnostics 的一致性，同时拒绝声称 PASS 却含清理异常的矛盾记录。不能用合法清理信号推断异常终止。
3. RESULT 的 `source_manifest_sha256` 是 source-map JSON 摘要，与 LAUNCH 的 manifest-file 摘要是不同域，分别核验，不盲等同。`reviewed_source_manifest` 则由真实 worker 传入 manifest-file SHA，必须与 LAUNCH 对应同一摘要。source map 必须前后相同，Attention summary 的当前 manifest/source map 也须对应同一组身份。这里未重新遍历源闭包或验证 ELF/runtime 映射。
4. 检查 RESULT 与 sibling algorithm seal/Attention summary 一致，且明确非 INCOMPLETE。这只是声明一致性，不是数组内容验证。
5. 同一只读 FD 一次解码并计算全文件 SHA，流式消费原 r3 `Decoder.records()`，不构建全部 records 列表。只有同一 decoder 达到真实 EOF、产生真实 seal，才与外部 `{records,raw_bytes,encoded_bytes,final_hash}` 逐字段比较。
6. wholeblock 校验外层 token envelope 角色，Attention 校验外层 event/exp 角色及 sequence。**payload 内容在本批仍是不透明字节**，没有解 token、operand、Dense 引用或 exp 数值。合成正例故意不伪装真实模型输出。
7. 两条流全部完成、元数据及文件读前/读后身份不变后，才返回有限成功。中途异常、缺 FINISH、尾随字节、空流、角色互换、外部 seal 错误或文件漂移均不发布部分 PASS。
8. Attention 的 `event_payload_sha256` 是逻辑摘要，不能当文件 SHA。文件 SHA 必须来自独立可信计划；本批明确未验证逻辑摘要。

r3 source pins：

- format.py：936f01ff9c7152c4752305c60c1442489f4fa8d71c08d7a38458d9f9690c76c5
- decoder.py：6f93cf8b6929a840f725c539a53a96f95e369b47920b4e36b4eaf0ac5d570f89

两源先在打开前检查 32 KiB 上限，再同 FD 有界读取并按 bytes 校验、检查读前读后身份，然后完整编译；decoder 的顶层 `format` import 被限定到此次加载的已 pin 模块，不静默复用外部同名模块。未弱化原 decoder 的 EOF、失败 latch 或原始限制。

## 本批测试的精确范围

保留原 16 个 unittest 方法，另增加 5 个 v2 合同方法。原覆盖包含正常双流、合法 anchored cleanup、20 项终态拒绝、15 项身份拒绝、缺失文件、错误 plan/pins/policy/JSON、路径 alias/hardlink、header/frame/metadata/payload/digest 截断、FINISH 后额外字节/第二 FINISH、四种重新生成 chain 的错误 terminal 总量、未关闭 context、合法空 codec 但组合拒绝、四种外部 seal 字段错误、角色互换、全文件 SHA 错、短读/nonbytes EOF/读上限、读后文件替换、import 隔离、codec 源读取前限额及 CLI 默认拒绝。

这些是验证器的合成单测，不是实际 wholeblock 或全部 r3 状态空间验证，也没有再次运行此前的 codec 大矩阵。更没有运行实际失败/失联的任何数值流。

## 明确保留的未完成项

- TokenRecordDecoder / OperandDictionaryDecoder / Dense lifetime 引用的组合语义消费。
- Attention canonical JSON、exp envelope、逻辑 digest 与算法图原始节点核验。
- 完整算法数组、presence/frequency、KV 拼接、实际调度/cache/ACK 同活对象关系。
- source/runtime/ELF 全闭包及全部终态资源台账的独立重核。
- 原策略 22 数值门及其余诊断/reference-only 范围；任何 exact-FMA 或 RTL 等价验收。
- 真实多 GB 离线扫描的吞吐、容量和资源资格。

因此本候选可用于拒绝明显缺终态、身份不一致、截断或伪封尾证据；它不是给旧未封流制造验收结论的工具。后续层级应保留独立 verdict，不能靠本批有限 PASS 自动晋级。


## 本候选的 v2 精确声明边界

只接受 Attention summary schema `fixed93-fullblock-attention-pv-reuse-observation-v1`，以下字段以精确 Python/JSON 类型和值检查，同时检查 RESULT 的嵌入 summary，避免 bool/int 宽松字典相等隐藏类型漂移：

- `normalization_evaluations_per_causal_key`：整数 1。
- `probability_use_repeats`：整数 8。
- `normalization_reuses_per_causal_key`：整数 7。
- `observed_normalization_reuses`：整数 693504。
- `scalar_schedule_changed` 与 `both_probability_domains_repeats_verified`：均为布尔 true。

LEC1 ordinary event metadata 只接受 `fixed93-attention-event-v2`，exp envelope metadata 仍仅接受 `fixed93-attention-exp-envelope-v1`。拒绝旧普通 event v1、v1/v2 混流及 exp-envelope-v2，不为旧版本设置双接受路径。未解析 payload，故这些检查并不验证 metadata 自述的真实事件种类、数值、重用次数或双 probability domain 内容。

合成 fixture 故意声明 693504，但每条流只有极少量 opaque synthetic bytes；693504 不是实际观测结果，也不是等量生成的数据。正例通过恰好证明容器 PASS 不能被当作数值/调度/算法验收。新增负例覆盖旧 plan、旧 summary、合同缺失与漂移、1/8/7/693504 的缺失/错误/float/string/bool 类型、布尔声明类型和 v1 混流。

本候选仍保持 manifest-file SHA 与 source-map SHA 分域、strict JSON、同 FD hash/解码、真实 EOF、真实 seal、非空流和外部原会话 terminal attestation 检查。它不依赖任何旧会话终态，不读取真实 run、reference、权重或模型 payload；没有启动 DUT、native 加速库、M128、模型或 RTL。

API 保持 `verify(root, plan_path, expected_plan_sha, terminal_path, budget_path, *, seconds=30)`，CLI 参数不变。旧 `fixed93-offline-container-plan-v1` 与普通 event v1 不向后兼容是此版本的故意边界。`SOURCE_MANIFEST.json` 冻结本目录五个源文件的 SHA/大小、来源 SHA 和 scope；`synthetic-test-result.json` 只记录本次小合成验证，二者均不是 source-qualified 或实际准入批准。没有 commit 或 push。

本次实际命令在 consumer 目录执行 `timeout -s KILL 15s python3 -I -S -B test_verify_evidence.py > synthetic-test-result.json`，exit 0；21/21 合成方法通过（原 16 方法 AST 相同），耗时 0.927 秒，maxrss 21924 KiB，单 CPU，拒绝操作尝试为空。该结果不扩大上述 scope。
