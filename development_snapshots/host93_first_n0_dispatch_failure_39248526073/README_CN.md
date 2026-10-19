# 首个 M128 N0：DISPATCH 前门实际失败摘要（39248526073）

## 证据与审核状态

- 本快照只保留原始 `summary.json`、`stage_exits.json`、`source_hashes.json` 三份安全 JSON，逐字节不变；另加本说明。未复制私有日志、权重、张量、二进制、系统清单或工作流/执行源码。
- Actual 独立审核状态：**ACCEPTED**，仅接受本次 reference DISPATCH 前门的实际失败证据；原 failure / INCOMPLETE 不变，不授数值、Host 或全块通过资格。
- 正式审核身份：review_first_n0_actual_39248526073_20261019T1203；MANIFEST.json 1852 B / 8f297a1e9891d999f2f01a80ad002701acde345638ab09a9538293588f0f49b2；SUMMARY.json 9361 B / 059b5eda5f5837ae6ae4bc060cc018b60d2e436b84787202a2aa2bd5fa82afeb；ACCEPT_ACTUAL_FIRST_N0_REFERENCE_DISPATCH_PREFLIGHT_FAILURE_ONLY。本 v2 仅补齐审核元数据，原三份安全 JSON 与 v1 完全一致；发布仍待最终五路径核验。
- [原 Actions run 39248526073](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/39248526073)，job `118046310718`，attempt `1`；实际执行 head `fd16bcf9dbcd9ea6ca54c35754d6aa51d8fba327`，终态 `completed / failure`。
- 本摘要基于发布父提交 `c4ecd4a4b77e85137eba5746f0c77f72b9e0e452` 生成；三份安全 JSON 的 82 个固定 `project_sources` size/SHA256 与该只读 checkout 全部相符。生成本候选没有重跑原生任务、下载资料、修改仓库或发布。

## 原始状态与阶段

原 `summary.status=INCOMPLETE`、`failure_category=INPUT_OR_CONTRACT`，总时长 `21.214023` 秒。五阶段依次为：

- `n0_wheels_acquire`：exit `0`，`2.206252` 秒。
- `n0_runtime_install`：exit `0`，`6.090402` 秒。
- `n0_raw_acquire`：exit `0`，`7.458911` 秒。
- `n0_inputs_prepare`：exit `0`，`1.064079` 秒。
- `n0_reference`：exit `1`，`3.626513` 秒；原阶段 `FAILED / NATIVE_SUPERVISION / CHILD_EXIT_NONZERO`。

五阶段均 `waitid_code=1`、`waitid_status=exit_code`、`final_reap_signal=null`，是自然退出；均无 receipt timeout，且 `cleanup_confirmed=true`。收据保留的 `kill_attempted=true / SIGNAL_SENT_BEFORE_REAP` 是监督清理记录，不改写自然退出结论。

## 精确失败边界与已知范围

- 唯一安全失败 marker 为 `NOT_COMPLETED:DISPATCH`。在已绑定的 `candidates/host93_first_n0_sources/reference/n0_reference.py:190`，唯一 `DISPATCH` 门要求 `report['observed_runtime']['capability'] == expected['capability']`；原 `PINS.json` 的固定要求为 `AVX512`。因此可定位为运行时 capability 与固定要求不相等。
- 实际观察到的 capability 字符串没有出现在本批三份安全 JSON 中；本摘要不推断其具体取值，也不以平台/硬件猜测补证据。
- 由该源码控制流可推得，到达此失败门之前，固定来源与官方类节点、原始 raw2 bytes/SHA、选定 `ci31214` Python profile 与解释器身份、五份 native library 文件身份及固定 runtime source 身份检查已通过；`OMP_NUM_THREADS=4 / MKL_NUM_THREADS=4 / OPENBLAS_NUM_THREADS=1 / PYTHONNOUSERSITE=1` 环境门、禁止 capability/ISA override 的环境门，以及 NumPy/PyTorch 版本和 torch commit 门已通过。这是安全 marker 与已绑定源码的控制流归因，不是另行公布运行时清单。
- `torch.set_num_threads(4)`、`torch.set_num_interop_threads(1)`、`torch.use_deterministic_algorithms(True)` 在第 191–193 行，尚未执行。第 194 行的 build-SHA equality、第 195–196 行的模块路径检查、官方 N0 forward，以及后续 output/identity/postflight 检查同样未到达。第 187–189 行构建 observed_runtime 字段不能当作后续 equality 门通过。
- 原 `summary.contract_failure.boundary=UNREPORTED`、`code=UNMAPPED_CONTRACT` 完整保留；不将本说明的源码归因回填成原 summary 已报告的合同边界。

## 资格边界

- `runtime_ready=true` 仅表示该 pipeline 的运行时安装前门完成，不代表冻结参考的完整运行时或数值资格通过。
- `inputs_ready=true` 与 `completed_components=['n0_runtime','n0_inputs']` 原样保留。固定 16 输入 receipt 检查已由 prepare/pipeline 控制流通过，只表示 `CANONICAL16_PREPARED_ONLY`，不是输入或权重已经加载到 RTL。
- `reference_ready=false`；`capture_state`、`comparison_state` 均为 `NOT_COLLECTED`，对应数据为 `null`。原 `n0_observation.state=COLLECTING` 是失败时留下的状态，不代表 Actions 作业仍在运行。
- 原八项 scope 全为 `false`：`cpp_compiled`、`cpp_generated`、`fresh_host_sv`、`n0_numeric`、`reset_launch`、`toolchain_build`、`toolchain_tiny`、`weights_loaded`。FIFO、后续 toolchain/Host/RTL/N0 捕获与数值比较均未执行；没有 N0 数值 PASS/FAIL 或 fullblock 资格。
- 这批变更边界仅为四个安全快照文件和进度文档的一次纯尾部追加；不包含任何工作流/执行源码修复，不触发或宣称重跑。
