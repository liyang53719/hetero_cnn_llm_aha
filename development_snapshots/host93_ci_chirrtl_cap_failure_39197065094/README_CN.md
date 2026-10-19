# 部分 PASS / 整体 FAIL：工具链与固定微例完成，CHIRRTL 文本大小前门拒绝

- GitHub Actions 39197065094，attempt 1，提交 43372bebcca86984be80029f8c13c05741ec7eb2，job 117882006421。三份安全 JSON 原字节保存。
- 协调器总记录 524.434364 秒。前 25 个阶段 native exit 0；host93_chirrtl 自然 exit 1，waitid code/status 1/1，未超时、清理确认，耗时 11.762095 秒。
- 工具链组件完整返回，toolchain_build 与 toolchain_tiny 为 true。六项 Host/数值/权重资格仍 false。
- 本轮统一失败诊断为 AVAILABLE。有限去敏尾明确报告 EmitCanonicalHost93.scala:26 的 requirement failed: 48 MiB CHIRRTL cap。固定源码先将 IR 转为 UTF-8 字节，再要求长度不超过 50,331,648；因此本轮内存 UTF-8 长度确定超过该值，确切长度尚未记录。创建输出目录及写 FIR 尚未执行，模块断言也尚未执行。
- 这是本轮文本上限合同拒绝，不构成 OOM、超时或算术错误证据。五条既有 Chisel warning 保留在安全尾中，未据此建立因果。前一轮无文本诊断的 CHIRRTL 失败原因仍未知，不倒填。
- 同 job 的 class/JAR/source 前置检查有控制流证据；本包不含这些私有实际文件，不声称独立重哈希。CPU 是阶段累计计数差值，RSS 是协调器累计 child 峰。
- 实际独审：review_host93_ci_all_stage_context_actual_39197065094_20261019T0409；MANIFEST SHA256 0e5a7b4696dc9a4d87fdf17dbb32cdbc44a0257684775b414989f3213437cd5b；SUMMARY SHA256 60737f6daf3215bf87f5e6eb246cad33d74e9acc9c59dcb26bbb4eb9884fd7a6。

仅保存公开源码身份、固定去敏诊断和安全摘要，无生成物、工具二进制、张量、完整日志或机器库存。原五次失败保留。
