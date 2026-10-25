# 重现边界与外部输入合同

本小包可独立检查源码、阅读脱敏证据和执行纯 mock。真实 normal import 需要原 Linux CPython 3.12、固定 runtime、官方 target、完整本地 manifest 与适用的独立审批，全部在包外。它不是 fresh-checkout 自包含 runtime，也不能称作 stdlib-only 的真实运行；只有证据工具与 mock 使用标准库，真实导入依赖 native Torch / NumPy 等。

## 原输入身份

- r2 CONFIG：fee441468e6a9201a7c604428934309c3140ad8ecf80f8c06f74d240a0be2651。
- r2 静态 REVIEW：c7df3d3079c2105eea8a29a194e42246cd78f5492746ec88d4db9ea5cebb3379。
- r2 cold01 RECEIPT：d810b6bac96f3e8bc44332e6ce74b7b9b81f5b9621860c95fce8d675d9a26d62。
- 独立执行 REVIEW：b0f18a0060e46b6f4575dd6315826f748365e47ab14443775a4cf820c83e6451。
- 原 CONFIG_V6：8c69c9fa5d641d07c0084a5010cc35734ade7e3b36f2760a3fede8548dbdac14。
- STATIC_RUNTIME_AUDIT baseline：2dae5e8d62646621ab4d2f7c13f2c90283bc201c85fbfe159873297515115064。
- INSTALLATION_VERIFICATION：81a747ef91ce5542f2e78745b9fb1655da8045ae2661379c823a46eb0d741e5e。

## prepare_gate.py 的实际接口

复用模式要求 --reuse-config 指向包外原 CONFIG_V6，且 --reuse-config-sha256 必须是上述确切 SHA；--output 是全新输出。它读取旧配置中真实本地路径、旧 gate 源码、被复用的 pinned closure 与原 probe source。此包没有旧配置完整字节、旧 gate 目录或 18,622 文件闭包，因此仅有本小包不能运行这条恢复路径。

初建模式接受 --target、--runtime、--runtime-baseline、--installation-receipt 和 --output。它需要真实 target 文件 inventory、固定 11 个 distribution 的 METADATA/RECORD、基线 native_pins、对应 CPython/stdlib、readelf 及静态系统库 closure。仅有版本号或摘要 JSON 不满足该接口；本包没有另造 baseline 生成器或未经审查的 bootstrap 脚本。

真实重建若迁移目录或替换解释器，路径相关 code/marshal 身份和完整 config/review 哈希也可能变化。必须重新建立完整材料、审查与适用权限，不能将逻辑角色替换回任意路径后宣称等同原审批，也不能用此包中的 summary 替换原 CONFIG。

## 依赖来源边界

12 个新 wheel 的确切官方 URL、SHA256、bytes 和 base requirement 范围已记录，但 wheel 内容未打包。原固定 11 runtime distribution 和 CPython/native 文件仅提供必要角色与 hash，不提供完整重装材料；原 Torch wheel 缓存也未被证明可得。PyYAML 6.0.3 来自已安装的真实 distribution metadata、原 RECORD 和校验后的复制文件，不虚构 wheel 来源。

所有真实重执行、配置或 Layer 构建、forward、数值 reference 和 DUT/matrix 工作均不在本包 mock 命令或历史 import-only 授权范围内。既有一次 claim 已消费；此文档不是重试授权。
