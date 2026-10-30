# 唯一 same-job 五 profile M128 calibration / LOCAL_DATA 工作流候选

仅本地源码草案；没有发布、activation manifest、workflow_dispatch 或 CI 启动。
基线是 actual acdb64b7bbeea7196311509a960ff0c0285d3a9a 已发布 LOCAL_DATA_R2 workflow/guard，不使用旧10月14工作流。

- 新触发路径唯一：`ci_launch/five_m128_samejob_calibration_20261030_once.json`。
- schema `FIVE_M128_SAMEJOB_CALIBRATION_LOCAL_DATA_ONE_SHOT_V1`；profile `FIXED4096_VECTOR32_FIVE_M128_CALIBRATION_LOCAL_DATA`；nonce `five_m128_samejob_calibration_20261030_once`。
- 先单独源码提交，再另审一个只有该manifest新增的启动提交。实际git diff-tree必须唯一A；恰好1parent==source_sha，event.before/after与source/launch一致，attempt1。无需并且不使用Actions事件省略的added/modified字段。
- 六字段identity保持source/launch分离，实际launch blob来自git；写RUNNER_TEMP，不随source checkout删除。artifact_name仅本地身份，不意味着上传任何binary。
- 标准ubuntu-24.04/350min、原exclusive concurrency group与原pinned checkout/upload actions不改。
- 第一个step（checkout前）保存SAME_JOB_START_V1 monotonic/run/launch/job_budget_seconds21000；prepare_and_run继承，不在build后重置deadline。
- 运行父任务实现的prepare_and_run.py与summarize_same_job.py；本小包不是完整可运行发布闭包。完整组合须独立审source/tool/material/owner/deadline后才考虑新activation。
- GH_TOKEN只在prepare controller step提供，controller必须仅向原bootstrap iDMA acquisition传入；其他子阶段/summary不得继承。workflow本身不证明controller已隔离，需组合source审计。
- summary step always运行；固定单一JSON校验≤65536B且regular/no symlink。只有summary校验成功才上传这一固定文件，防止always上传无效/超界残留。无glob、日志、binary/SV、weights/reference输出路径。保留14天。
- 流程exit2仍INCOMPLETE/非green；没有continue-on-error，不把有限同刺激标定冒完整模型或最终RTL PASS。
- 实际preflight由controller执行：13GiB MemAvailable、20671240864B free、原image/JDK/AVX512等。不足应NO_GO，不擅自降低或重试昂贵任务。

测试：5项normal/-O。包括实际acdb R2原209B launchfixture SHA541b3e5fc92f43d0cf39d21df531c9e44af989177ba694cea726b9bf1545fa25；保留真实source10a30bcf...与launch ef6a5fcd...不同。另在临时Git仓库实际两个commit运行新CLI、核身份/唯一blob；仅标准库+本地Git，无网络写入/编译。
