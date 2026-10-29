> NEW P0 producer evidence integration: old same-dir BLOCKED notes below describe previous baseline. This candidate consumes ACTUAL_FRESH_DRIVER_DEPENDENCY_V1 from the future fresh producer, auto-hydrates P0 metadata, and keeps gate/up REQUIRED_UNOBSERVED. No new numerical PASS; see ../ci_frontend_pipeline_r2_20261029/P0_SOURCE_EVIDENCE_CN.md for exact proof boundary.

# 五 profile 原物料链 → V3 → same-job consumer：NEW 接线候选

状态：源码/轻量 metadata 和 control-flow 回归；未下载、运行 Torch、EDA、DUT、CI 或发布。完整 Chisel/RTL 数值接受不因本候选变化。

## 真正接线位置
`prepare.py` 复用原 selected materializer 全部函数；仅 main：
1. 原 repo dependency pins 核验。
2. `connect_bundle.preflight` 核本 job 刚生成的 build result / shared artifact / run/source/launch。P0缺独立bindings/evidence或actual source mapping即在昂贵runtime下载前拒绝。
3. 原 runtime安装 → selected完整权重 → 原program bytes → 独立official full128 reference → 原provider/TSV。没有软件DUT算术替代，不注入参考expert IDs。
4. 原 `runtime_bundle.json` V1 保留原字节，调用 `connect_bundle.connect` 写独立 `runtime_bundle.v3.json`。P1–P4只升级schema，无P0观察豁免；全部原profile/inputs/refs/provider/limits保留。
5. P0在原emitter后实际调用锁定 `correct_observation_policy.apply`，独立验证12anchors与20→18唯一四行delta，保存sidecar和retained evidence metadata，调用原 `attach_bundle.assemble` 与R3全部source/receipt/role/header校验。缺真实证据只有UNADMITTED，绝不发布准入bundle；gate/up永远REQUIRED_UNOBSERVED/INCOMPLETE。
6. 最终 `consumer.load_binding` 与same-job build provenance通过后，原子no-clobber发布新V3；`CONSUMER_ARGV.json`提供真正消费该V3的argv及validate-only argv，**不自行执行DUT**。外部scheduler负责剩余预算与严格owned-job监督。

## 具体复用接口
同一 future owning CI job 在原 build 完成后取原producer实际输出：
```
python <NEW_PACKAGE>/prepare.py --repo "$CHECKED_OUT_SOURCE" \
 --output "$JOB/profileN" --profile N \
 --artifact-manifest "$BUILD/frontend/frozen_artifact/frozen_artifact.json" \
 --artifact-manifest-sha256 "$PRODUCER_MANIFEST_SHA" \
 --local-build-result "$BUILD/frontend/BUILD_ONLY_RESULT.json" \
 --local-build-result-sha256 "$PRODUCER_RESULT_SHA" \
 --expected-run-id "$GITHUB_RUN_ID" \
 --expected-launch-commit "$REVIEWED_LAUNCH_COMMIT" \
 --expected-source-commit "$REVIEWED_SOURCE_COMMIT" \
 --local-runtime-abi "$OWNING_STARTUP_ABI_RECEIPT" --local-runtime-abi-sha256 "$ABI_RECEIPT_SHA"
```
P0另必填 `--p0-bindings <12项源/原program路径JSON> --p0-bindings-sha256 ... --consumption-evidence <原producer retained三项证据索引> --consumption-evidence-sha256 ...`。Evidence index从实际producer既有pin关联retained文件；本候选不会制造它。索引原件不改，复制到profile目录并重新核SHA。程序paths应指本次真实provider原program，不能参考输出冒充。

五次N=0..4必须同一manifest SHA/binary/SV/source/driver；不能按profile重新elaboration。调度不能把四路准备成功报成五块通过。当前公开successful BUILD_ONLY run40862676969只有summary保留，**没有可复用binary/完整result**，这里不会从summary构造假的产物或download证明。

## 数值/资源不变
- 4096 Matrix MAC、32-lane共享Vector、M128；旧16lane PASS不迁移。
- P0=12张93,595,648B；P1=14张43,111,008B；P2=11张36,705,280B；P3=18张1,685,402,304B；P4=15张1,672,492,032B。首先验证原70张metadata；每MoE保留全256专家。
- 原FP32/BF16顺序与reference、原Torch topk/IDs不变；small-ID契约待用户，不绕过tie差异。
- 原P0 AVX512、8GiB free、参考RSS3GiB、每profile20000s/18000CPU/12GiBAS/1e9cycles保留。全5×20000不可能保证350min，scheduler必须基于实际remaining time和DUT速率另做admission，不能盲降limit。
- 没有weights/NPZ/probehex/完整dump上传功能，物料与真实输出仅本地/CI按需生成。失败唯一证据不自动删除。

## 最小剩余证据
- P0 actual shared source_manifest尚缺12anchors映射与retainedcompile/constructor身份闭包；真实split-driver/include目录不满足R3收窄same-dir合同。保持BLOCKED；仅增加自述mapping不足。
- 原0.8/35B参考运行/runtime安装未在freshjob执行本接线；轻量tests不能代替它们。
- 同job startup runtime ABI模块 f6826a38f3d479b18a45f8bd2d80ff20a7eb2c77ba1783f77a5abf612308632c 已按原字节接入。外部owning job必须先在strict supervisor下调用原 runtime_abi.py CLI --execute-reviewed-loader-list 获取真实receipt；这里只核receipt，未执行loader。prepare前置与consumer执行前后均验证binary/tool/loader/library/cache/alias，执行环境显式clean_env；仅startup identity，不覆盖later dlopen。原binary不执行也不从当前工具环境推断其依赖。
- 真实完整block DUT数值、周期利用率、90%与最终RTL均没有新增证据。

## 测试边界与临时文件
`test_connection.py`运行真实metadata/load_binding函数，binary/ref数据为明确mock；验证四路V1→V3同manifest、原V1不变、P0缺证据拒绝、外部ref/错profile/错run/降limit拒绝，以及preflight先于runtime/物料调用。`test_original_prepare.py`沿原6tests验证70tensor完整性、MoE256专家、selected program bytes与reference/provider routing；只调用原程序生成纯Python，不调用Torch/硬件。
首次复制遗漏 `DEPENDENCIES.json` 被原test捕获，已复制原完整文件修复；失败log保留。`__pycache__`不交付；未清理已有用户/运行/唯一数据。

## P0前置边界与ABI测试说明
P0 preflight只保证metadata参数齐全、pins以及actual source manifest具有映射入口；它不是完整R3准入。split-header/错program等仍由原provider后corrector与load_binding拒绝，可能已有准备成本，但不发布V3且不启动DUT。独立3项P0完整metadata连接测试使用真实锁定TSV/源码/程序，mock producer receipts/ABI：成功路径18observe及required gate状态保持；split-header/错program拒绝。没有真实硬件数值证据。
连接测试ABI边界明确mock，另直接对复制的原ABI模块运行其parser/receipt tests；均无真实loader运行。execute函数相对R3仅新增env=clean_env，其余AST不变。scheduler对全job/repo live-byte census、实际remaining wall与reviewed未压缩上界另行admission；本候选不会用压缩大小冒安装上界。
