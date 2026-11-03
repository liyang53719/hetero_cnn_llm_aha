# P0 default_v1 reference-only：TEMP 源码候选

本目录是独立的新执行身份 `P0_QWEN2_FULL128_DEFAULT_REFERENCE_V1`。只准入一次隔离 GitHub-hosted Linux x86_64 / CPython 3.12 job。源码发布本身不启动执行：本提交没有 `ci_launch/p0_portable_reference_default_20261103_once.json`，工作流只响应该文件的新建。另一个仅新增该文件的提交，明确引用前一源码提交及 SOURCE_MANIFEST 的 SHA256，才可启动；rerun attempt 不为1拒绝。source/launch/run identity 分开记录。

## 状态与范围

- 当前只完成源码实现及纯 Python / synthetic / mock 测试，没有实际下载、安装、Torch forward、RoPE 生成、DUT 或 EDA 运行。仍是 TEMP，不是 reference PASS，更不是硬件数值 PASS。
- 新 job 不接触已有的运行 owner、资源、缓存、lease 或 retained reference；仅创建当前 run_id 的全新 owned root。不存在借用旧运行资源或旧 AVX512 qualification 的路径。
- 不改旧 AVX512 profile/installer/工作流。原 profiles.json 原字节复制，历史 profile 的 AVX512 字段仅作为冻结身份；新执行的请求为 default，实际 ATen API 必须返回 DEFAULT。
- CPU affinity 与 Torch 线程数不同：新 supervisor 保留本次从 OS 读取并固定的完整允许 CPU 集合，实际 Torch intra-op=4、inter-op=1，四个线程环境量=4。不声称该 affinity 与历史运行相同。DEFAULT 不是 scalar-only，MKL/oneDNN 仍可能使用硬件 SIMD。

## 固定输入与实际计算

FROZEN_P0.json 的固定 SHA256 为 `e93e1a8ff6e54f7f82ddd3d0134785350a09726e257c2cb73b6823625fa09c76`。它不是本次输出生成的 expected。

- 原 Torch 2.10.0+cpu、git 449b1768410104d3ed79d3bcfe4ba1d65c7f22c0，Transformers 4.40.1。26 个分发 wheel（25 runtime + pip）共238,463,458字节全部按独立历史 SHA 验证；只安装 Qwen2。原 sidecar 由这些 archive 内容再导出，核对原序列化 SHA；实际 import 的6模块和12 native 文件再验固定 hash。
- 原 checkpoint revision ba1cf1846d7df0a0591d6c00649f57e798519da8。先验证原38,536字节 safetensors header，再顺序获取12原权重的精确 range，总93,595,648字节。每个权重历史 SHA 在进入 reference 前独立验证，不能把新下载计算出的 digest 当 expected。单 response≤8MiB，无自动 retry。
- config 原 SHA a58e896d2756a7947f23f3db55667c19ca3b8524188a30c8c640cd7ff72a5136；seed34930816；M=128；hidden1536；FP32 storage。
- 原 run_reference 主数学路径保持：FP32 decoder constructor 和完整32768 RoPE cache，然后 BF16 module；strict assign 原权重；eager、deterministic/highest、autocast关闭；实际调用原完整128-token forward两次，每次新冷cache。第一遍无hooks，第二遍原hooks；输出与完整KV cache仍直接byte相等。
- 每个原save点在写bin前独立检查 name/shape/dtype/bytes/SHA256。第一次不同即停止，并留下只有名称/计数/hash/布尔值的内部检查摘要。baseline actual SHA在原baseline固定检查之前已记录。成功必须24名称完全相等、10,650,624字节、11 module-call各一次。
- RoPE用原完整32768 FP32 constructor→BF16→截1024→FP32存储，实际重新生成 `[2,1024,64]`、524,288字节，固定 SHA4060acc13a636cbd303e96552df99033cd348f238025f11bae1bc0fcab32c815；两128前缀仍与本次已通过冻结hash的reference输入直接byte比较。
- 最终再验所有源码、runtime wrapper/sidecar/native、12权重、24实际输出文件与完整RoPE，成功也只表示这个固定fixture全部可见原字节序列SHA256严格一致。不证明所有内部算子顺序、未捕获中间舍入或其他输入等价。不更换 golden 或容差。

## 有限资源和终态

从 checkout 前单一 monotonic 起点计时，整 job wall≤3600s。controller+已准入子树 CPU计费≤3600s；每阶段使用 max(waited-child CPU, observed-tree CPU)，再加 supervisor/controller CPU，不重复累加。GitHub checkout/action 自身的 CPU 不在 controller RUSAGE 覆盖内，不能宣称完整 runner cgroup CPU计量。export 前记录整job wall/CPU，写出口后再核上限。CI另设65分钟硬超时兜底。

|阶段|wall上限秒|CPU上限秒|aggregate RSS|per-process AS|阶段树|
|---|---:|---:|---:|---:|---:|
|runtime|1800|1800|3GiB|4GiB|6GiB|
|weights|600|120|512MiB|2GiB|6GiB|
|reference|600|1200|3GiB|8GiB|160MiB|
|rope|120|120|1GiB|4GiB|16MiB|
|finalize|60|60|256MiB|2GiB|6GiB|

表中为包括监督/cleanup/验证的上限；worker工作额度再扣40秒保留原cleanup最多30秒及RSS证据核验最多5秒，global remaining更紧时优先缩短。阶段串行，每阶段启动前真实 MemAvailable 与cgroup-v2各祖先剩余额度取最小，必须≥该阶段RSS+1GiB；运行中保留1GiB。初始磁盘free≥8GiB，持续reserve≥1.5GiB，完整新owned树≤6GiB；只扫描此树。阶段单文件reference/RoPE≤128MiB，其他≤2GiB；旧阶段安装大库不误用当前stage128MiB上限。

单rawlog≤32MiB、gzip≤16MiB、RSS日志相同，tree entries≤150000。原 pidfd/process-group/observed-descendant cleanup、lossless日志、RSS telemetry 复用为新目录源码副本。新supervisor只有明确的affinity、cgroup有效余量、全局预算及stage/aggregate文件范围差异，旧源码不变。

实际要求 native_exit=0、errors空、`COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP`、observed remaining空、reader join、pipe EOF、gzip finalized、RSS文件完整验证。任何失败不继续后续计算。cleanup未知标INCOMPLETE，保留root；原数值first cause不被cleanup问题覆写。仅保证原process group及已观测稳定身份，不声称抓到两次采样间逃逸/setsid全部后代；RSS/CPU/disk为采样限制，可能超调。waited-child CPU补充已reap后代，但不能成为全OS/cgroup containment证明。

若launch身份不合法、owned输出路径已存在/不可信、或截止时间已耗尽，fail closed，可能没有安全出口；绝不为凑摘要去覆写/借用未知root或延长deadline。普通已获owner的失败尽力产生三JSON。任何失败都不能准入后续build。

## 唯一对外出口

仅 RESULT.json、CHECKS.json、HOST_RESOURCES.json。逐文件≤64KiB，总≤128KiB，固定字段/名称/enum/type/有限数值，拒绝duplicate keys、unknown字段、NaN/Inf、bool冒充int、symlink/hardlink/额外文件。检查顺序按原save顺序验证，首diff后不准出现后续已执行项。

上传前还必须通过私有TERMINAL seal，精确绑定run/source/launch与三个JSON的hash；PASS额外要求GitHub实际controller步骤outcome=success。写出JSON后alarm或最终预算检查失败留下的旧PASS不准上传。seal始终留job本地。

只导出已允许的25项摘要、12权重计数、实际host/预算/终态。真实tensor值、bin、权重、SV、raw logs、绝对路径、URL、异常自由文本均不导出，也无base64/hex载荷、目录打包、glob或fallback上传。工作流上传精确三个filename；source中没有DUT/provider/build/EDA job。

## 源码发布与下一次执行

SOURCE_MANIFEST.json枚举本候选所有文件和唯一新workflow的字节数/SHA，不包含自身避免自引用。其外部SHA由另一次明确launch输入钉住。当前publication INPUT只允许这些新源文件，在父任务重新核实的main上新增；主线发布与唯一激活均由父任务处理。需先完成最终源码独立审查，再做一次reference-only云端执行。任意bytehash不同的结论就是新default候选不符合旧fixture，停止，不改golden。
