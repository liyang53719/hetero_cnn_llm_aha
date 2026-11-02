# TargetDir 官方 API 修复的有限证据

原云端 B run 41419416366 五准备阶段和全源码编译成功，emit native 1；仅有 BEFORE_ELAB 与有限异常类别，未获得其具体异常栈，不能追认其唯一首因。

本地同官方 API 的 32-bit 寄存器+Boring 微型模型，原绝对 TargetDir 在 elaborate 后、Compiler.toLowFirrtl 的 requireTargetDir→os.RelPath 确实拒绝。最小修仅将 annotation 改为相对于 os.pwd 的路径，并验证解析后严格等于原绝对输出；不 chdir、不改原模型/参数/LOW或SV存在门。

0931 原失败保留。0934 两源码类型编译与微型完整五 API 正例严格通过；其 LOW/SV/harness 仅为微型模型，不是 B 产物。新 EmitOnly 已类型编译，但大 B 尚未重新 elaboration/运行。本次不授协议、矩阵数值或完整块 PASS。

有限故障诊断仅固定阶段/类别、已知源码 basename 和正行号，继续抛原异常；无原错误消息、路径、权重、张量或 raw log。
