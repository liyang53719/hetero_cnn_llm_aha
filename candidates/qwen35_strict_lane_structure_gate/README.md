# StrictFp32MatrixLane 既有 CHIRRTL 结构预检

## 本批结果与边界

本目录只增加可复用的纯 Python 结构预检入口，不修改原 runner，不运行 JVM、编译器、firtool、仿真器，也没有重新 elaboration。实际检查的是上一批已经生成且来源/类加载经过资格检查的单 lane CHIRRTL：319,324 字节，SHA-256 为 `ea7b84533c96641771bd58ba97a10898d428fc6782b1ced726442ada0320eb7d`。

`EXISTING_IR_RESULT.json` 记录该既有 IR 预检通过：StrictFp32MatrixLane 顶层，全部且仅有 9 个模块可达，各访问一次，8 条实例边，无环；完整端口、方向和寄存器形状符合既有 scope；恰好一个变量乘法原语，其两个具名输入均为 UInt<24>。IR 内没有 extmodule、intmodule 或 blackbox 标记。没有将原始 IR、类文件、原始日志或私有机器路径放入本目录。

这不是硬件数值/异常标志测试，不是 RTL 或真实握手测试，不是综合后的物理乘法器数量、面积或 Fmax 证明，也不是阵列集成证明。既有 HardFloat 与旧 C++ flags 接受条件差异没有被解决。

尤其：不能把本次 PASS 当作未来测试 runner 的新 elaboration 使用了同一电路；`new_runner_same_circuit_proven` 为 false。本 gate 单独不能开放新后端执行。下一阶段若执行新 runner，必须另行获取并核对该次新 elaboration 的实际 IR 与来源/类资格证据，不得只复用本结果。

## 如何 fail-closed

1. 从既有 `qwen35_strict_lane_chirrtl/run_chirrtl.py` 提取冻结哈希对应的 `need` 和 `validate_ir` 两个 AST 函数；不导入或执行原 runner 的入口和任何其他顶层语句。没有另造完整 FIRRTL parser。
2. 冻结原 parser、IR_SCOPE、公开资格摘要、具体 IR 及四个私有资格回执的字节数和 SHA-256。入口先校验所有证据，再检查结构；错位、变动、缺失均失败。证据哈希是对上一批资格结论的精确引用，不声称本批重新检查了所有源码和 class。
3. 在原精确端口/边/乘法/寄存器检查上增加显式遍历，检查全图可达、无环、无重复实例名、模块各实例化一次，以及 24×24 输入类型。
4. 可选注解文件必须是空 JSON 数组；所有非空注解均拒绝，包括 BlackBoxInlineAnno。未提供注解时，只报告该 IR 文本自身的结构，无权宣称外部不存在注解。
5. 每个文件及直接 IR/注解输入上限 1 MiB，读取前后检查文件身份和元数据；单 CPU，256 MiB 地址空间，10 秒 CPU/实时时限，禁止子进程与网络。失败以异常和非零退出码终止，不产出 PASS。

原 parser 会忽略许多不相关 body 行，不是通用 FIRRTL 安全验证器，也不保证任意输入语义有效。生产入口对整份已知 IR 的精确哈希绑定是必要条件。`structure()` 仅供该入口及合成负控使用，不能独立给未冻结 IR 发资格证明。PINS 与代码需要作为受审核的共同信任基线；任意修改二者不属于本证明。

## 复现

在仓库根目录运行：

```sh
python -I -S -B candidates/qwen35_strict_lane_structure_gate/controls.py
python -I -S -B candidates/qwen35_strict_lane_structure_gate/gate.py "$QUALIFIED_WORK"
# 如有实际配套注解，必须显式传入，当前仅接受 []：
python -I -S -B candidates/qwen35_strict_lane_structure_gate/gate.py "$QUALIFIED_WORK" "$ANNOTATIONS_JSON"
```

`QUALIFIED_WORK` 是上一批保留的私有资格工作目录，必须包含 `ir/StrictFp32MatrixLane.fir`、ELABORATION_RESULT.json、CLASS_LOADING_SCOPE.json、IR_SCOPE_RESULT.json、RESULT.json。公开仓库不携带这些私有证据，只有合成 controls 可以无私有证据运行；不要伪造回执来“复现”。本次实测 Python 3.12.14 / Linux。

## 测试覆盖

`CONTROLS_RESULT.json`：27 个测试方法全部通过。21 类合成 IR 负控包括：断开的隐藏 extmodule/intmodule、重复模块/电路、缺失电路、错误实例语法、未定义目标、循环、重复实例名/链、断边、意外模块、错误乘法宽度/输入、常量输入、嵌套第二乘法器、缺失乘法器、隐藏内存、空 IR。另有 6 个非空/畸形注解拒绝变体、IR 与注解尺寸上限、合成结构即使匹配也不能冒充冻结 IR 的哈希检查，以及正常合成结构/显式空注解正控。

负控是人为构造的 parser 输入，不是新生成硬件。`MANIFEST.json` 只列本目录可公开文件的有限字节数和哈希；不包含自身以避免递归哈希。
