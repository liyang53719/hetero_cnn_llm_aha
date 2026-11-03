# TEMP：恢复原 AVX512 的 P0 reference-only 一次验证

## 已发生的实际结果与本次边界

- 原 same-job run 41702967626 在 CPU_AVX512 前置门失败，未进入 build。原 FULL session 97358 终态仍未知；本包不触碰、重启、删除或借用它的资源。
- DEFAULT run 41720209902：runtime 通过，weights 前检失败，reference/RoPE 未开始。后续 header-only run 41732318207 返回 HTTP 206，原 38536 B header SHA 与 12 项 metadata 全匹配；这只证明当次路径，不证明原失败全部因果。header source 7ca8b6b6 的普通 CI 41732031755、activation 61dc8aa3 的普通 CI 41732318377 均成功。
- DEFAULT repair source 39fe2f8d67e346e7bf9e973480eabc3e7ba833ee，activation 5e3dc9f54f977f36b59254a88045e42d16499db8；实际 run 41734412224 明确 FAIL / REFERENCE_HASH，普通 CI 41734206925 与 41734412259 成功。原 12 权重全通过。第 16 个执行检查 stage.self_attn.0.1 是 BF16 [1,12,128,128] attention probabilities，393216 B，dtype/shape/长度一致；expected SHA 375523468652eec0a4765d67c08506ab1d441bdfe3dd69ef55d7ec0d0323335d，actual SHA 3d41c4fa2751977f12e6a088c71d21d97f46f23fe5a0880d143bb602ccd4ed1b。15 项 PASS、1 MISMATCH、9 NOT_REACHED。
- 第一遍无 observer 的完整输出及 KV bytes 已相同；第二遍在 attention 返回 hook 即停止，post-attention layernorm、MLP、最终 cache/output 与独立 full1024 RoPE 未通过也未执行完。Q/K/V projection 和 o_proj/attention output exact 不蕴含 probabilities exact。不能据此声称两遍完整 forward 相同、DEFAULT portability 合格或已证明差异仅来自 softmax。
- 实际三 JSON ZIP 3228 B SHA 3e8538f03d3570c1422c0289df2056438b991ab562112a18c7df69e63c0644b6。此失败保留；本新命名空间不修改 DEFAULT 文件，不改变任何 golden/tolerance，不把已失败的身份改成 PASS。

## 唯一新身份与实时门

- 候选身份：P0_QWEN2_FULL128_ORIGINAL_AVX512_REFERENCE_V1。新工作流与一次 activation 路径 ci_launch/p0_original_avx512_reference_20261103_once.json；launch schema P0_AVX512_ONE_SHOT_V1，显式绑定 default_failed_run_id=41734412224、新 source commit 及其 SOURCE_MANIFEST SHA。source 包不含 activation/nonce。
- 固定 ATEN_CPU_CAPABILITY=avx512，实际 Torch API 必须为 AVX512。没有 DEFAULT/AVX2 fallback，没有随机重试或自动再排一次；旧 once 文件不得重用。
- 在同一新 job、runtime 下载/安装之前，读取当前 Linux /proc/cpuinfo 和 os.sched_getaffinity(0)，在所有 admitted CPUs 的 flags 交集要求 sse2,avx,avx2,fma,avx512f,avx512dq,avx512bw,avx512vl。这比旧 avx512f 最低门保守，不是执行新 CPUID 资格框架。缺任一项则 FAIL / CPU_AVX512，weights/reference/RoPE 均不启动。源码标明这是 OS 暴露的物理 ISA 证据，不拿 forced Torch API 名称替代它。
- 全部已准入 affinity 原样保留，父及子进程在各阶段核对。CPU affinity 是可调度 CPU 集合；Torch intraop=4、interop=1 和四个线程环境变量是另一组设置。新 affinity 不声称与历史机器相同；也不声称硬件、系统或内部算术顺序完全相同。
- 实时物理门通过即可在该 job 安装原固定 runtime、验证 import/native、运行权重与 reference/RoPE。仍没有 DUT、build、provider、EDA。

## 原始数值与输入闭包不动

FROZEN_P0.json SHA e93e1a8ff6e54f7f82ddd3d0134785350a09726e257c2cb73b6823625fa09c76 保持逐字节不变。它继承自 DEFAULT 候选，顶层 candidate_id/execution_identity 是该冻结包的来源元数据，不是本新 job 的准入或实际身份；本代码不读取 execution_identity 来选择 dispatch。新 manifest、runtime、wrapper、实际 API、RESULT 身份单独明确 AVX512。

- 原 checkpoint ba1cf1846d7df0a0591d6c00649f57e798519da8，原 config、profiles、stimulus，seed 34930816、M128、hidden1536、FP32 存储；BF16 decoder/计算接口不变。
- 原 12 权重 93595648 B：下载后与历史固定 SHA/几何逐项比对，reference 使用前再核，非“新下载新 digest 自证”。不扩到其他 profile。
- 原 26 wheels（25 runtime 加 pip）238463458 B；Torch 2.10.0+cpu / git449b1768410104d3ed79d3bcfe4ba1d65c7f22c0，Transformers 4.40.1，原 6 imported module 与 12 native file pins；sidecar SHA 17d159b19e98d6f104bbaba1bd62ea2de96b5bcde8185230135c6a96d445628f 不变。不借用旧 runtime 或旧 wrapper 解释器绝对路径。
- 原官方 FP32 constructor/full32768 RoPE cache → BF16 module；strict assign 原 12 weights；同一输入、两个独立 cold cache 的 full128 forward，原 hook 与即时 raw-byte snapshot。第一个完整 baseline，第二个 observed；24 项 shape/dtype/bytes/SHA 在每个 save 前硬门。任何 mismatch 先留固定摘要再立刻中断，不写该 mismatch tensor 文件，不进入 RoPE 或 EDA。
- 原 full1024 RoPE FP32 [2,1024,64]，524288 B，SHA 4060acc13a636cbd303e96552df99033cd348f238025f11bae1bc0fcab32c815；保持 full32768 constructor、BF16 转换、原 call/table，并核128前缀。
- 最终 PASS 仅代表本次 24+1 可见数据全部字节相同且资源/归属/终态完整，不证明所有未观测 functional intermediates 或内部 op order，更不是五块模型或 DUT 通过。

## 有限资源、终态与唯一出口

沿用已独审 controller/supervisor/cleanup：job wall 3600 秒从 checkout 前计，controller 加 children CPU 3600 秒。runtime/weights/reference/RoPE/finalize stage wall 分别1800/600/600/120/60秒，CPU1800/120/1200/120/60秒，RSS3GiB/512MiB/3GiB/1GiB/256MiB；实际资源检查、子进程AS/CPU限额、disk reserve、owned-tree limits、lossless bounded logs 与 owned-group cleanup 不减弱。checkout/action CPU 不计入该 controller CPU 数字；采样有已有的精度边界。

只允许 RESULT.json、CHECKS.json、HOST_RESOURCES.json，单个≤64KiB、合计≤128KiB，固定 typed schema/enum。private terminal seal 绑定本 run/source/launch/default-failed lineage、三文件 hash 和最终预算；PASS 还须真实 steps.controller.outcome=success。无 seal、错 hash、末尾 deadline/alarm、错误 outcome 均拒绝上传 PASS。仅传三 JSON，不传二进制、weights、tensors、SV、raw logs 或编码载荷。不会绕过已有二进制上传否决。

本次本地仅源码、AST 与 pure/mock negative tests，不联网、下载、安装、真实 framework import、reference/RoPE、EDA 或发布。父负责唯一 source publication 和之后独立一次 activation；当前 main/base tree 必须在发布前重新 CAS 核对。
