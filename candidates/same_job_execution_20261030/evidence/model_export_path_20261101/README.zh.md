# 原身份导出路径故障

41314704781 的 20 个构建阶段均有原 Actions 有限 native0/完整清理/EOF 摘要。构建步骤正常结束后，独立 export 步骤沿用旧 frozen_artifact 目录，而实际 candidate pack 固定输出 model_candidate_artifact；实际 FileNotFoundError，上传未开始，Artifacts API 为空。

这不等于取得七件产物，不能继承丢失的 ELF 或数值通过。修复固定目录且校验结果清单路径必须精确落在固定目录，不接受自报任意路径或旧目录回退。原完整验证/严格收尾/七件非空门和预算均不变。
