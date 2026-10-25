# 官方 M128 实际 reference pair01（独立增量）

状态：实际进程 exit 0，reference capture 和自检已记录；独立执行复核 16724 项检查、0 失败。原公开包已通过独立技术审查；最终发布复核另行绑定。此增量不是新的执行许可。

本包以公开 r2 source/mock 提交 `9e4d51f1acf8f5ac62326c6dd3ec54d2ab8fc9ff` 为依据，只新增路径，不修改旧 20 文件、M16 或任何失败证据。旧 r2 的 60 CPU 秒 / 90 秒仍是冻结提案，不能把本次结果回写成其执行 PASS。

## 已实际执行的范围

官方 Transformers 4.40.1 原完整 Qwen2DecoderLayer，保留原 max_position_embeddings=32768、rope_theta=1000000。同一个 layer、同一组原输入对象，baseline 后 observed 两次完整层 forward。一次真正 cold chunk 128，原 embedding rows 0:128，不复用 M16/旧 M128 输出。不是完整 Qwen2Model/ForCausalLM forward。

实际返回 y/prob 的 native bytes 逐字相同；三个边界的原输入、参数、buffer 原对象及 native hash 保持不变。baseline 没有 Observer、module hooks 或 capture trace，但安全 profile 仍开启。29 个中间值只来自 observed，不能宣称全部 baseline 中间值无干扰。

独立执行复核以 JSON/stat、流式 opaque hash 和 y/prob 原字节比较进行，不重新数值计算 29 项自检。模块/maps 只是快照，不是全生命周期或所有 live code 身份证明；动态 torch-git 无文件来源仍明确未证明。Python audit/profile 不等于内核隔离或 native/未 profile 线程无法绕过的证明。

全部 29 个 observed 字段通过已记录自检。FP32 softmax 共 1536 行，row-sum 最大误差约 1.95e-7（门 2e-5）；future 的 97536 个概率为正零。这里不是 DUT/256 比较、不是 numeric acceptance，也不是 RTL 或硬件性能结果。输出哈希是本次新生成身份，不是运行前 oracle 的正确性证据。

## 实际资源与语义

worker + cleanup 记录 48.158060528 秒；user+system CPU 50.368487 秒。采样 tree RSS 峰值 568340480 B，不是硬 RSS cap；RUSAGE_CHILDREN 另有不同口径的高水位，见 RESOURCE_OUTCOME.json。120 秒是 worker 进程含线程的 CPU hard limit，不是内核聚合进程树配额。180 秒是轮询阈值，加 cleanup=2 秒语义，不是 kernel hard deadline 或最终总墙钟 ≤180 的严格资格。

完整私有 manifest 在 worker 外前后各 hash 18652 项、1016158675 B；分别约 1.026 / 0.953 秒，均无差异。最终目录含父 receipt/seal 共 66356782 B ≤ 83886080 B；stdout/stderr 均 0 B。成功 seal 是完成 size/hash 检查后最后一次不改字节的 rename。失败诊断可超过成功输出门且不得删证据凑门。

## 文件与复核边界

- SOURCE_BINDINGS.json 绑定旧公开源码和本次 exact sources。仅 gate_common.py、worker.py 两个原字节后像新增在 runtime_source_overrides/；其他六个文件字节未改。
- PROFILE_LOGICAL.json 是不可执行的逻辑投影；不是完整私有 CONFIG，也不带 GO/approval/claim 能力。
- INPUT_AND_TOOL_PINS.json、OUTPUT_IDENTITIES.json 只含逻辑 shape/dtype/byte-count/hash，不含 tensor、weights、raw output、maps 或私有绝对路径。
- SELF_CHECKS_SUMMARY.json 归纳既有自检与三边界证据，不在公开包生成期间重新做数值运算。
- EVIDENCE_BINDINGS.json 给出原件 hash，公开投影不是原件。实际执行独审与公开投影审查是两道不同审查。

## 本地可复现条件（不是执行授权）

取得合法可用的同 hash 原始 13 输入、原 config、完整闭包的 Python 3.12 / torch 2.10.0+cpu / Transformers 4.40.1 和已 pin 官方源码；版本号本身不足以重建完整闭包。公开包不分发这些原件，也不保证另一 CPU/build 位精确相同。

在新的私有目录组合旧 r2 的六个未变文件及本包两个后像，重新绑定当地绝对路径及所有 source/runtime/input hashes，重做完整 exact config/review 和资源/冲突核查，取得新的独立执行授权与单次 claim 后才可运行。旧审批、旧 claim 和本次成功不能复用。不得在旧 source/mock 或已封存输出目录上就地重跑；公开命令只给占位符形状，不能直接执行。

本增量的准备仅 stdlib 读取 JSON / source、hash 文本、stat 文件和核对 metadata；没有重新 import ML、构造 layer、forward、native/DUT 或读取 tensor 数值。历史原失败不删、不改、不掩盖。
