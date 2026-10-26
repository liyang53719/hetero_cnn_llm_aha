# 原 Matrix 功能模型后端：有限证据候选

本包不是五块 prefill 完成报告，不切换生产顶层或已发射 RTL。保留原固定8×512资源定义；行为后端真实计算有限 FP32 FMA、更新状态并遵守握手，不读取预存参考结果。

## 已完成的层级
- 11 源 typecheck：39 新类；纯 Scala 两 suite、7 case 通过（合成 AST/状态/对象回调，不是真实 service）。
- 65,536 次 live FMA 单冷 JVM 循环：230,879,664 ns。仅成本样本，`numerical_qualified=false`，不能外推 M128 可行性。
- 原 StrictFp32MatrixLane / HardFloat / Treadle：74 组有限 BF16 FMA 位值和 flags，一 case 通过。
- 官方 AST 桥另2源 typecheck：4 新类；不等于 service 通过。

## 两次 service 失败均保留
1. 原文本解析 FAIL，未构造 factory，也没有原 IR 字符串文件。
2. 官方同次最终 prepared AST 路线在 CPU120 门终止，0/1 case；清理完成。prepared 文件存在仅提供源顺序下界，不能证明最终 ABI gate、factory、engine、reset、反馈或事务完成。

seeded feedback 尚未资格；全块数值/五 profile M128/RTL 回放均未完成。官方 source 只用精确 URLs/hash 引用，不上传第三方源码或 class/IR/工具/权重。13 Scala 保留原字节，分别属于11源后端与2源官方桥；后继观测修复不混入。本目录为独立 candidate overlay，不是根目录生产接入。

复现详见 REPRODUCTION.json：角色化 argv 只说明精确还原条件，不是已独立验证的 hermetic 脚本，也不授权自动执行各阶段。
