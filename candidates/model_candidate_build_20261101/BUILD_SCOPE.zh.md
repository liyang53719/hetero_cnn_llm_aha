# TEMP：统一 RMS32 模型候选的一次构建与身份观察

本入口是原始 Chisel 模型新硬件候选的编译后端收集，不是完整数值通过，也不是最终冻结 RTL 回放。旧生产 HIGH/SV/数值接受门不修改。共同硬件仍为 4096 Matrix MAC、共享 32-lane bank，五块只换运行配置和数据；lane 存在不等于全链 II=1 或 80%/90% 利用率已达成。

## 不可自授接受

- `MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1` 永久保留 `UNREVIEWED_MODEL_BUILD`。
- 固定源合同只允许指定原源替换/新增、原矩阵子模块与 bank 子树、真实有序 122 typed ports；实际 HIGH/LOW/SV descriptor 记录新身份，但不会把实际值自行填写为已接受基线。
- 下载后必须外部独立审查实际源码/结构/完整 provenance，再由可信 cloud invocation、预算与审批 pin 绑定 `model_candidate_review`。仅允许模型数值评价，不继承旧通过或最终 RTL 接受。
- 原 Torch 路由与 FP32 运算顺序、逐步 BF16 舍入、Qwen2 FP32 存储不更改。参考数据复用须独立 DATA_REFERENCE_ONLY 契约和完整字节重新验证。

## 实际执行边界

同一 fresh GitHub job，原 20 阶段，严格 O1/非 fast-math/禁止 FP contraction，单份源码、SV、ELF。GitHub 不执行五块数值或下载模型权重/参考。仅上传原七类文件：ELF、同源 SV、driver、source manifest、tool manifest、build receipt、frozen manifest；不增加日志、IR、classes、权重、NPZ。

新版 source manifest 整文件最多 16 MiB，包含 HIGH canonical/module/完整有序 annotation 信息、LOW 完整 typed ports、SV fingerprints、结构观察与实际阶段收据。其余原单文件限制及七件总 4 GiB 限制保留。接收端核可信 API/digest/ZIP 清单、尺寸、类型、路径和逐文件 hash；ELF 初始 0600，无自动执行。执行前仍须静态 readelf/资源账单和严格实际 ABI。

## 预算不扩大

整个 workflow 9000 秒；20 阶段构建共享 7200 秒且包含最多 1800 秒准备；900 秒保留给导出。workflow 声明步骤共 147 分钟、job 150 分钟。bootstrap 与各阶段同时检查实际剩余预算；所有阶段各自最大值相加不能保证在 7200 秒内全部可达，不足时必须 INCOMPLETE，不扩大阶段资源或重试。旧 BUILD_PLAN 的 21000 秒字段仅验证历史文档身份，新入口不采用该执行上限，也不接受缺省 job budget。

## 当前验证范围

本目录源码测试、微型 AST 与 helper 编译不代表 Host 完整 elaboration、五块 M128 或最终 RTL 已通过。生成合同硬 pin 只有最终独立源审后方可冻结；此源包不包含启动文件，源码发布本身不会运行重任务。
