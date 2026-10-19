# 原首 M128 N0：自然 AVX2 不符原 AVX512 前门的实际失败（39255764538）

## 状态与证据

- [原 Actions run 39255764538](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/39255764538)，job 118070526536，attempt 1，head `6322568f426af70115a313d5f5bf708df4c648ea`，终态 `completed / failure`。
- 本快照仅保存原 `summary.json`、`stage_exits.json`、`source_hashes.json` 的完整原字节及本说明。没有私有 receipt、完整日志、权重、张量、二进制或系统清单。
- Actual 独立审核：ACCEPT_ACTUAL_FIRST_N0_ORIGINAL_AVX512_GATE_AVX2_OBSERVED_FAILURE_ONLY；review_first_n0_actual_39255764538_20261019T1259，MANIFEST.json 1016 B / 0cb4e1ae4c14938cfc572d246e8bd80af54e6d763cc8fa5a32dfe808a18dc042；SUMMARY.json 7125 B / e04273ae5fff00333a07786543cd058a2ef542a4c5b0391bc377004c542d29f4。原实际 `INCOMPLETE` 与 `INPUT_OR_CONTRACT` 保持；本次不是 N0 数值 FAIL。
- 三 JSON 的 82 项 project_sources size/SHA256 已与该发布父只读 checkout 逐项核对。候选制作未运行任何 native、下载资料或修改仓库。

## 本次实际观察

协调器报告用时 `19.598964` 秒，不含 checkout/setup/upload。按原顺序：

- `n0_wheels_acquire`：自然 exit 0，2.288087 秒。
- `n0_runtime_install`：自然 exit 0，6.194777 秒。
- `n0_raw_acquire`：自然 exit 0，5.630626 秒。
- `n0_inputs_prepare`：自然 exit 0，1.083759 秒。
- `n0_reference`：自然 exit 1，3.628454 秒；`FAILED / NATIVE_SUPERVISION / CHILD_EXIT_NONZERO`。

五阶段均 `waitid_code=1`、`waitid_status=exit_code`、`final_reap_signal=null`、`receipt_timed_out=false`、`cleanup_confirmed=true`。`kill_attempted=true / SIGNAL_SENT_BEFORE_REAP` 保留为监督清理记录，不改写其自然退出。

原安全尾明确 `NOT_COMPLETED:DISPATCH`；新有限投影为 `reference_capability={state: AVAILABLE, expected: AVX512, observed: AVX2}`。这是本次已核源码从私有失败 receipt 投影的固定枚举，不是重新测量硬件或公开运行时清单。原私有 receipt 未上传，本地未独立重读。

## 源码定位与资格边界

- 原固定 `n0_reference.py:190` 的唯一 DISPATCH 门要求自然能力枚举等于原 PINS 的 AVX512。本次实际 AVX2 与该要求不符；原门、原双 SHA、数值算法和精度没有降低。
- 该门前的 Python/原固定库身份及版本、环境准入已由到达唯一 marker 的控制流关联；仍不声称完整参考运行时准入通过。线程 set 4/1、deterministic 设置、build-SHA equality、官方类编译与 forward、输出及双 SHA 后验均在该失败门之后，未到达。
- 原 `contract_failure={boundary: UNREPORTED, code: UNMAPPED_CONTRACT}` 不回填；能力枚举是单独的安全观察字段。
- `runtime_ready=true / inputs_ready=true`、已完成组件 `n0_runtime/n0_inputs` 只表示安装和 canonical16 准备阶段完成；`reference_ready=false`，capture/comparison 均 NOT_COLLECTED。输入和权重未加载到 RTL。
- FIFO、工具构建、Host 发射/编译、DUT、N0 捕获/比较均未开始，八项 scope 全 false；不授数值、fullblock 或硬件兼容资格。`COLLECTING` 是失败收据状态，不代表作业仍运行。

## 停止与历史事实

按本轮既定规则停止，不自动重抽 runner、不再次启动原 43 阶段，也不改原 AVX512 门。继续需要满足原冻结 profile 的可用执行资源，不能靠本次失败降低准入。

独立候选 39252523415 的自然 AVX512 与原双 SHA 一致事实继续保留；它没有被采纳为原基线或传给 DUT。本次观察不能倒填更旧 39248526073 的未知 ISA，也不能保证下一台 runner 的能力。

本次五路径仅原安全证据和两份说明文档；没有 workflow/源码改动，不触发新的 Host/native 作业。普通文档 push 仍可能运行 guard。
