# 首 N0 raw 输出目录兼容后继（TEMP_SOURCE）

原 run 39246774912 在第三阶段网络前失败，原安全尾 RAW_OUTPUT:RAW_RULE_014 精确指向 acquire_raw.py 的历史 work 路径分量禁用门。实际展开的 RUNNER_TEMP 路径未出现在本批三份安全 JSON 中；本批不复制 Actions 日志中的机器路径。原三 JSON 与完整限定见 development_snapshots/host93_first_n0_raw_output_failure_39246774912。原 summary 的 UNREPORTED / UNMAPPED_CONTRACT 保留。

本后继只改原 Host workflow 的私有输出根为 /tmp/host93-first-n0-${run_id}-${run_attempt}，在既有绑定步骤核 run_id 全为数字、attempt=1 和根路径精确值，并让 actual、safe verifier 与三 JSON 上传共用 HOST93_PRIVATE_ROOT。原 raw 拒绝门、fresh/disjoint/no-symlink 门、全部生产 Python、43 阶段、原共享 6600 秒与预算、参考双 SHA 和数值容差保持。原 source artifact ZIP 仍走 RUNNER_TEMP。新 actual 状态 NOT_EXECUTED，未授 N0 数值或全块资格。

新增可移植 test_raw_output_boundary.py 显式接收 --repo、--workflow、--base-workflow 三个绝对路径；入口先固定 size/SHA，再从同 buffer 编译。真实 stage_entry.main 继续执行原 raw 同 buffer loader、完整 check_sources 与 prepare_output；只有 strict_opener 用测试哨兵在网络前停止，collect_fixed 被禁止。11 normal + 11 -O 通过：精确 /tmp 形式接受至网络前边界；work 祖先或叶拒绝；workspace/work-root 不误拒；已有输出、缺父目录、符号链接、仓库内输出仍拒绝。正例的 RAW_ACQUIRE:UNEXPECTED 是有意测试截停，不表示获取成功。未下载张量、执行 native 或重跑 runtime。

运行冷测时，--workflow 指向本次固定工作流；--base-workflow 使用 ccdd46b8fcac78834dd462f00a821c9430b3f7d2 中 .github/workflows/host93-ci-recovery-once.yml 的原字节（5179 B，SHA 0878fdfa6c13891be297a5e942dcce5cfbac491e4b92488097e743be43a5a4c7）。可以从该 Git 对象导出到调用者新建的临时文件；测试不依赖本机候选目录或自行访问网络。使用 python3 -I -S -B，另以 -O 同测。

本后继 SOURCE 有限审核通过：review_n0_raw_output_workflow_source_20261019T1153，MANIFEST.json 2609 B / 8ab1f343ea7c2eb08215b0d989ac1e61ad90bd5da41b599dc93f688b90957a85；SUMMARY.json 2688 B / b030cc9b8d9f1bb781f1fb7af9a442ddabf76a5a52e7eab385418f886ae8deb1；SOURCE_GO_FIRST_N0_WORKFLOW_FIXED_TMP_ROOT_ONLY。原失败 actual 独审已封，见 STATUS 与 SOURCE_PLAN。发布包含纯源码测试和安全说明，不发布完整日志、权重、张量、包体或二进制。
