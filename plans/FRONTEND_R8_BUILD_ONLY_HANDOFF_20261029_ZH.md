# R8 已验 frontend 交接：下步实际 compile/link（TEMP，2026-10-29）

## DONE：精确限定 frontend-only 范围
- 唯一[运行40838373693](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/40838373693)，job123328481240，attempt1；source `c16f379d3458b65de07ff2dd5538dc50fe62eb97`，launch `b522a4583d5887d2b3e8c1a6d6f374159c19d03a`。两提交身份不能混用。
- 21阶段 actual native0/errors0；4个物理frontend全部完成且完整EOF/cleanup。包含155 Scala编译、原始high、typed canonical/annotation/transform、实际SV发射、受限SourceInfo目录规范化identity、FMA/subset、串行真实物理provider codegen。
- 实际TopSV raw SHA `c8e6b1c8faf26831d46daea019b70347c1ae441621aa6de3ed69c14b38fd2f53`（222,202,215B）；normalized SHA `6555ede34ba2980a6ebfddb13325ffb14734063d3253fdadd493bfcb4bf67bb5`。仅允许已审SourceInfo目录变化，不放宽其他注释/pragma/string/语义。
- Host334.145911s、RSS9,596,116,992B（约9.596GB，8.937GiB）；实际313个SV参数已含原始iDMA wrapper。Down127.344356s、RSS4,784,238,592B。
- 生成文件1312个/1,228,129,994B，inventory SHA `44ebeb4330f2b94c4f99e89dc2b5b858cdd6a40564ecb06eac0e6627cc06e1b0`，只保存hash摘要；不能把生成C++等同编译或运行。
- 公开artifact12882657188仅受控summary：ZIP SHA `673850ecff6d37524b0075362523526534f055736e3029a35f9acdfe1b250508`，summary SHA `9b9a13d8424574c49f90f5378592ad91d296c6038413e47dcb9d2973d5005c88`（39591B）。没有把完整SV/CPP、权重或NPZ上传。

## ONGOING：NEW BUILD_ONLY 提案，尚未执行
同固定4096MAC/共享Vector32源码和provider定义，重新生成临时frontend后直接条件审查实际Host.mk/85端口/完整文件闭包、冻结derived pins，再按原生make顺序编译三子archive、Host archive及链接。禁止make隐式重启frontend；统一-O0，不改BF16/FP32算术，不用DPI/software/config-only驱动替代。不是等待手工获取已销毁runner的Host.mk，也不是再发起一个frontend-only资格任务。

七文件artifact冻结同一binary、Top/FMA/providers/includes/native flags/wrappers完整source身份、tool/driver/build receipts，五profile后续消费同一manifest。新阶段全流GCC/link受控错误摘要让超8MiB后的实际错误可见；仍受原job预算、磁盘/日志/RSS与清理契约限制。计划及源码在NEW `one_job_build_only.py` / `bootstrap_build_only.py`，待独立审查及唯一新身份批准后才能启动。

## TODO / INCOMPLETE，不冒通过
- 完整C++ compile/link、可运行binary：尚未建立；不要继承R8作为binary PASS。
- 五块完整M128原始Chisel数值 **0/5**：Qwen2-1.5B典型block、Qwen3.5-0.8B L0/L3、Qwen3.5-35B-A3B L0/L3均待同binary真实执行。Python/reference/provider资格不是DUT数值资格。
- 数值通过后才冻结同刺激并最终RTL回放；最终RTL数值仍 **0/5**。
- 有效MAC≥80%、争取≥90%仍是完整block/固定4096分母目标；本次没有RTL利用率实测，codegen时间/RSS不构成MAC利用率。
- MoE小专家ID同分契约未获批准，原Torch基线不改；更长token第二档1024/1224待明确，不阻塞M128。
- R7 Host两条原错误的确切文本不可恢复，保持UNKNOWN。已确认源闭包漏原iDMA wrapper并恢复原hash，不将后继成功回填成原错误文本已证。
- 旧未发布R8提案曾因陈旧materializer误回退truststore路径被独立review拦截，未写远端；最终重基包保持已验adoptium路径及所有旧守卫。
- 无本轮临时数据自动清理；保留源码/失败/原身份证据。74项原任务账本不因frontend-only自动改done。
