# L9.4 / L5.6d-P3 本地 Agent 交接 V720

日期：2026-09-02
仓库：`liyang53719/hetero_cnn_llm_aha`
审计起点：用户声明的 `main@11483e863b6d0f17885258aaab5e8cfd6e63b0dc`
审计时远端 HEAD：`a9ac2b1cdcc6bda27cb4be1dfc210d4edd43f11b`

## 1. 当前结论

`11483e8` 可以接受为 **L5.6d/P3 llama.cpp HETERO backend 功能等价的软件仿真闭环**，但不能接受为真实设备、完整 Command128 RTL payload 或 all-row RTL 闭环。远端后续的 `37eb90c` 已按这一边界重新分类，`a9ac2b1` 又为 full-logit 文件补了字节数和 SHA-256 来源。

已经闭合的事实：

- 原始 958-node llama graph 被 HETERO backend 接收，只有 1 个 backend split；
- 588 条 Command128 manifest 覆盖 28 层、7 组；
- 338 个 canonical GGUF binding，其中 281 个是原始 storage bytes，57 个是显式 F32→BF16 RNE 后的 canonical bytes；
- scheduler 记录 `cpu_fallback=0`；
- 软件 backend 连续执行 28 层并产生 28 个 checkpoint；
- completion callback 层面有 28 completions、7 stalls；
- 输出 argmax=7559，Top-10 overlap=10/10；
- 独立 RTL command/event fabric smoke test 接受并完成 588 条命令，engine count 为 Matrix/SFU/KV=252/308/28；
- 独立真实数值 endpoint 测试执行 `l0.input_norm` 与 `l0.q` 两条命令，1568 个 BF16 值 bit-exact，并对两个 endpoint 的 output-ready 做随机回压。

尚未闭合：

- llama backend 没有把 588 条命令传给 RTL command frontend；
- `cpu_fallback=0` 不等于没有 host CPU 执行，当前仍使用 CPU buffer 和 C++/OpenMP payload；
- 588-command RTL smoke test 的 engine completion 是 delayed echo stub，descriptor/L2 端口被 tie-off；
- 两命令真实 endpoint 的 payload 由 testbench 直接喂入，descriptor/L2 同样被 tie-off；
- 完整 21-command layer-0、真实内部 Matrix/SFU/KV 回压、非 host buffer、无文件中转、全 588 条真实 payload、actual full-logit 指标和 L10 physical signoff 均未闭合。

## 2. 本次沙箱新增

新增或增强：

- `src/heteronpu/logits_parity.py`
  - 默认严格检查 151,936 项完整词表（CLI 默认值）；
  - 稳定 Top-k：数值相同时低索引优先；
  - 区分 NaN、±Inf，硬件验收默认要求全部 finite；
  - 修复全零向量 cosine 应为 1 的边界；
  - 记录 little-endian float32 文件字节数、元素数和 SHA-256；
  - 文件字节数不是 4 的倍数时直接拒绝。
- `src/heteronpu/l9_transport_contract.py`
  - 固化 layer-0 的 21 条命令顺序；
  - 解码 128-bit word，核对 engine/opcode/roots；
  - 核对 21 条 event wait/signal 链、descriptor root binding、9/11/1 engine count 和六阶段覆盖；
  - 明确该结果仅是 static manifest contract，不是 RTL execution。
- `src/heteronpu/rtl_transport_evidence.py`
  - 将 588-command command-fabric stub smoke 与 2-command real numeric endpoint 分成两个证据等级；
  - 识别 L2 tie-off、host-fed payload、endpoint output backpressure 与完整内部回压之间的差异。
- `src/heteronpu/l9_payload_coverage.py`
  - 从当前 endpoint 源码提取支持 opcode；
  - 形成 21 条命令的逐项覆盖和实现 bucket。
- 新 CLI：
  - `scripts/audit_l9_4_layer0_contract.py`
  - `scripts/audit_existing_rtl_evidence.py`
  - `scripts/report_l9_4_payload_coverage.py`
  - `scripts/run_l9_4_evidence_audits.sh`
- 新机器可读报告：
  - `reports/execution/SANDBOX_AUDIT_A9AC2B1_V720.json`
  - `reports/execution/NEXT_ACTION_V720.json`
  - `reports/execution/L9_4_EXISTING_RTL_EVIDENCE.json`
  - `reports/execution/L9_4_LAYER0_PAYLOAD_COVERAGE.json`
  - `reports/execution/L9_4_SANDBOX_FIXTURE_RESULT.json`
  - `reports/execution/SANDBOX_FULL_LOGITS_TOOL_SELFTEST.json`

沙箱单元测试共 23 项全部通过。fixture/self-test 报告都有显式标志，禁止把它们当作真实 llama 或 RTL 闭环证据。

## 3. 严格禁止事项

- 不新建分支；只在 `main` 上工作和推送。
- 不把 `cpu_fallback=0` 写成“没有 CPU 执行”。
- 不把 57 个 F32→BF16 RNE canonical binding 写成“原始 GGUF bytes 未变”。
- 不把 delayed completion echo 写成 Matrix/SFU/KV payload execution。
- 不把 TB 直接驱动的 `sx/sw/mpa/mpb` 写成 descriptor/L2 transport。
- 不用 reference hidden state、reference output 或阶段文件替换待测模块输出。
- 不以 argmax/Top-10 代替完整词表指标。
- 不在同一精度模式下复制独立乘法器阵列；Matrix 路径继续复用融合阵列。

## 4. 接手前同步与防并发

```bash
git switch main
git status --porcelain       # 必须为空
git fetch origin
git pull --ff-only origin main
BASE=$(git rev-parse HEAD)
echo "$BASE"
```

确认 V720 文件已经存在。若远端尚未包含本次沙箱提交，则对附件 patch 执行：

```bash
git am --3way /path/to/hetero_cnn_llm_aha_L9_4_V720.patch
```

应用后仍停留在 `main`：

```bash
test "$(git branch --show-current)" = main
git status --short
git log -3 --oneline
```

若远端 HEAD 已前移，不允许 reset/force-push；先 `git pull --rebase origin main`，解决冲突后重跑全部验收。

## 5. T0：先在真实仓库重跑本次工具

```bash
PYTHONPATH=src pytest -q \
  tests/test_p3_backend_evidence.py \
  tests/test_l9_transport_contract.py \
  tests/test_rtl_transport_evidence.py \
  tests/test_l9_payload_coverage.py

bash -n scripts/run_l9_4_evidence_audits.sh
./scripts/run_l9_4_evidence_audits.sh
```

### T0 验收

- pytest 全 PASS；
- `L9_4_EXISTING_RTL_EVIDENCE.json`：
  - 588 frontend dispatch/completion；
  - delayed echo stub=true；
  - submission L2 tie-off=true；
  - real payload commands=2；
  - endpoint output backpressure=true；
  - full 21-command payload=false；
- `L9_4_LAYER0_MANIFEST_CONTRACT.json`：
  - total=588；
  - layer0=21；
  - Matrix/SFU/KV=9/11/1；
  - event wait=0..20、signal=1..21；
  - errors=[]；
- `L9_4_LAYER0_PAYLOAD_COVERAGE.json` 与源码一致，不能手改成 PASS。

## 6. T1：关闭 actual full-logit 指标

使用真实运行产生的文件，不得重新生成“看起来一致”的替代文件：

```bash
ACTUAL=work/results/llama_hetero_full_graph/logits.bin
REFERENCE=work/results/llama_cpp_qwen2_baseline/pytorch_logits.bin

test -f "$ACTUAL"
test -f "$REFERENCE"
test "$(stat -c%s "$ACTUAL")" -eq 607744
test "$(stat -c%s "$REFERENCE")" -eq 607744

PYTHONPATH=src python3 scripts/compare_p3_logits.py \
  --actual "$ACTUAL" \
  --reference "$REFERENCE" \
  --expected-count 151936 \
  --relative-l2-max 0.01 \
  --cosine-min 0.9999 \
  --output reports/execution/L5_6D_P3_FULL_LOGITS_PARITY.json
```

### T1 验收

- `status=PASS_FULL_LOGITS_PARITY`；
- `count=151936`，两侧全部 finite；
- argmax 两侧相同且应与现有结果 7559 一致；
- Top-10 overlap=10；
- relative L2≤0.01；
- cosine≥0.9999；
- actual/reference 都有 607744 bytes、151936 elements、SHA-256；
- 报告由真实路径生成，不能提交 sandbox self-test 代替。

## 7. T2：把两命令 endpoint 改成 descriptor/L2 payload shell

当前 `tb_qwen2_real_payload_endpoint.sv` 直接驱动 49,152-bit RMS payload 和 Matrix step，且 fabric 的 L2 端口 tie-off。先不扩命令数，先让现有两条命令经过真实 payload shell：

```text
Command128
  -> command_event_frontend_sram
  -> descriptor root fetch/decode
  -> Shared-L2 read request/response
  -> RMSNorm / Matrix endpoint
  -> result packer
  -> Shared-L2 write
  -> completion
```

优先复用：

- `descriptor_public_record_decode.sv`、现有 descriptor context；
- `qwen2_shared_l2_rms_payload.sv`；
- `qwen2_shared_l2_matrix_tile16_payload.sv`；
- `qwen2_tile_idma_expand.sv` / `qwen2_tile_dma_plan.sv`；
- `qwen2_sfu_command_endpoint.sv`；
- `qwen2_matrix_command_endpoint.sv`；
- `hetero_l3_command_fabric.sv`。

允许在 reset 前将 GGUF/输入数据装入模拟 DDR 或 L2 memory model；start 后禁止 TB 直接驱动算子 payload。reference expected 值只能用于 checker，不能注入 DUT 数据通路。

### T2 验收

- 2 accepted / 2 completed，event 1、2 顺序正确；
- descriptor fetch 数、L2 read/write grant 均 >0；
- `sx/sw/mpa/mpb` 不再由 TB 在 active run 中直接驱动；
- delayed echo stub completion=0；
- RMS 1536 + Matrix 32 共 1568 BF16 结果继续 bit-exact；
-随机化 descriptor response、L2 response、endpoint output-ready；每类实际 stall>0；
- protocol/macro/watchdog/error count 全 0。

## 8. T3：扩展到完整 layer-0 21 条真实命令

### 8.1 当前覆盖

| 类别 | 命令数 | 当前状态 |
|---|---:|---|
| 已真实数值测试 | 2 | `input_norm`、`q GEMM` |
| Matrix opcode 已接受但 feeder/descriptor/writeback 未闭合 | 8 | K/V、QK、PV、OProj、Gate、Up、Down |
| 第二个 RMSNorm 可复用但未测 | 1 | `post_norm` |
| SFU opcode endpoint 未实现 | 9 | 3×bias、2×RoPE、Softmax、Attention residual、SiLU×Up、final residual |
| KV Command128 adapter 未实现 | 1 | `kv_append` |

### 8.2 推荐模块拆分

- `qwen2_layer0_payload_orchestrator.sv`
  - 只做 command ownership、descriptor transaction、engine route、writeback 和 completion；
  - 禁止包含大段数值组合逻辑。
- `qwen2_matrix_payload_sequencer.sv`
  - 根据 descriptor 生成 GEMM/QK/PV tile/step；
  - 共用现有 Matrix fused array；
  - 每条 command 完成最后一 tile 写回后才发 completion。
- `qwen2_sfu_command_endpoint_v2.sv`
  - opcode 0x32 RMSNorm：复用现有核；
  - 0x30 Vector：bias add/residual；
  - 0x34 RoPE：复用 RoPE descriptor/context 与数据通路；
  - 0x33 Softmax：复用在线 Softmax，禁止落地完整 score matrix；
  - 0x35 Activation：SiLU(gate)×up；
  - 一个 active command + 子引擎 ready/valid mux，不复制浮点/乘法资源。
- `qwen2_kv_command_endpoint.sv`
  - 将 opcode 0x41 的 descriptor 转换为 `kv_tensor_stream_endpoint` cfg/stream；
  - 检查 tensor id、format、last BE、beat count 和 address range。
- `tb_qwen2_layer0_21command_real_payload.sv`
- `scripts/run_qwen2_layer0_21command_real_payload.sh`

### 8.3 六阶段 checkpoint

必须至少输出：

1. input norm；
2. Q/K/V projection + bias + RoPE；
3. KV append storage image；
4. QK + online Softmax + PV + OProj + attention residual；
5. post norm + gate/up + SiLU multiply + down；
6. final residual。

每个 checkpoint 包含 shape、dtype、bytes、SHA-256、max abs、relative L2；BF16 packed output 还要给 bit-exact count。不得只记录最终 hash。

### T3 验收

- 21 accepted / 21 completed；Matrix/SFU/KV=9/11/1；
- 无丢失、重复、乱序、event error、completion status error；
- descriptor roots 全由真实 588-record manifest 提供；
- descriptor/L2/DMA/Matrix/SFU/KV 各自至少一次随机 stall；
- no hidden reference injection；start 后 host payload drive=0；
- 六阶段 checkpoint 全存在且通过数值阈值；
- KV staging bytes 与 reference bit-exact；
- QK/Softmax/PV 走在线路径，不生成完整 score matrix；
- command completion 只由真实 engine done 触发，不得保留 echo stub。

## 9. T4：把 llama HETERO backend 接到真实 transport

当前 backend 仍是 monolithic C++ software submission。把 backend path 改为：

```text
GGML graph split
  -> 588 Command128 + descriptor table
  -> device command queue / RTL frontend
  -> device buffers + DMA/Shared-L2
  -> real engine completions
  -> logits device buffer
```

要求：

- 自定义 `ggml_backend_buffer_type`，不再返回 CPU buffer type；
- 权重允许一次性 host→device upload，但中间激活、KV、checkpoint 不经文件；
- `hetero_qwen2_submit_588` 不再调用 generic C++ layer backend；
- completion callback 只消费真实 device completion；
- 提交日志区分 command-queue stall、descriptor stall、Matrix/SFU/KV stall；
- 提供 build/runtime 计数器证明 software stage dispatch=0、host file transport=0。

### T4 验收

- 原始 958-node graph、1 split、scheduler fallback 0 保持；
- backend→RTL/device 21-command canary 先通过，再扩全量；
- host CPU buffer type=0；
- generic C++ layer calls=0；
- inter-stage file opens/writes=0；
- actual full-logit gate重新 PASS。

## 10. T5：扩展到 588 条 / 28 层 / 7 组

### T5 验收

- 588 accepted / 588 completed；Matrix/SFU/KV=252/308/28；
- 28 层连续、7 组连续，无每层回到 host；
- 每层 completion/checkpoint 28 个，顺序和 hash 正确；
- Matrix、SFU、KV 内部 stall 均 >0；
- no loss/dup/reorder/event/protocol/watchdog errors；
- software stage dispatch=0；host file transport=0；
- 最终 151,936 logits 通过 T1 全指标；
- 报告必须写清 functional RTL/device 边界，不能提前宣称 all-row physical signoff。

## 11. T6：仅在功能闭合后做 L10

沙箱无法运行 ARM memory compiler、`bifrun`、真实工艺库、DC/Genus、P&R、PVT/OCV/SAIF。由本地环境执行：

- summary storage SRAM macro replacement；
- command/event/descriptor SRAM macro 数量与容量核对；
- all-row integrated RTL；
- 1 GHz synthesis/STA；
- post-route PVT/OCV；
- SAIF/VCD 动态功耗。

### T6 验收

- 无 inferred giant register array 代替目标 SRAM；
- macro count/capacity 与 architecture budget 一致；
- setup/hold 在规定 corners 全通过；
- 面积、频率、功耗报告带工具版本、库 corner、约束、commit SHA、日志 SHA；
- 功能回归与综合网表/门级仿真一致。

## 12. 最终提交与推送

所有任务继续在 `main`：

```bash
git switch main
git status --short
git add -A
git commit -m "feat: close L9.4 descriptor-backed Qwen2 layer canary"
git pull --rebase origin main
# 重跑 T0/T1/T3 验收
git push origin main

git rev-parse HEAD
git ls-remote origin refs/heads/main
```

最后两个 SHA 必须完全相同；报告中记录 push 后 `main` SHA。禁止 `--force`。
