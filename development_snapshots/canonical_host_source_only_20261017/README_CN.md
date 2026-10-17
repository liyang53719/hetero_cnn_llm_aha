# Canonical Host 小批源码历史快照

状态：SOURCE_ONLY 历史快照。仅保存项目源码及有限冷测证据；Git 提交或发布状态不改变源码证据等级。

这是从已审项目源码中选择的独立、缩小范围候选。它只保存两个逐字不变的源文件及独立的小型冷测，不代表原先任何更大包通过审查，也不撤销任何此前阻塞或公开许可问题。

## 内容与用途

- `axi_protocol.hpp`：手写外部协议观察代码，包括 AXI 采样数据结构、独立收支/债务账本。它不是生成的 C++ 模型、算术引擎或可综合 RTL。
- `hold_contract_cold.py`：小型 Python 控制契约，描述首个可见完成快照、稳定保持、零债务、累计活动不变和实际 ACK 释放条件。它不是 C++ 实现或真实硬件观察器。
- `test_source_only_cold.py`：新建的最小测试，只检查本目录源码 hash、Python 语法、有限源码文本条件，以及上述 Python 契约的小型合成正反例。

两份原项目源码来自 `production_canonical_host_cpp_skeleton_v2_20261017`，保留原文件名、注释和全部字节。先前独审结论是 `GO_SOURCE_ONLY_UNCOMPILED_INTERFACE_SKELETON`；这里只继承两份源文件的来源，不继承整个旧包的运行、metadata 或交付结论。具体项目源 hash 见 `PROJECT_SOURCE_HASHES.json`。

## 独立运行

在本目录执行：

    python -B test_source_only_cold.py
    python -B -O test_source_only_cold.py

冷测只需标准语言运行时，无原工作目录、canonical 数据、metadata、provider 或参考数组依赖。`axi_protocol.hpp` 的标准头引用是正常源码引用，本目录不记录任何已安装系统文件、工具链、头文件或库的位置、版本或 hash。

## 边界

- Python 模型：仅小型合成控制契约测试；没有完整 block 模型或数值运行。
- C++ 源码：只保留和做有限文本检查，没有编译、链接或 C++ 行为执行证据。
- RTL：没有 elaboration、仿真、绑定、capture 或资源/时序证据；完整 block RTL 仍为 0/5。
- 此片段不是完整 driver、完整 HostMemory 或通用 AXI 验证器。读取账本使用全局 FIFO；本目录不证明跨 ID 乱序响应，也不包含完整五通道稳定性监控。
- Python helper 的类型注解不是运行时输入验证；`normal_result` 使用 Python 值相等语义。冷测不把它当作严格外部数据类型校验器或真实设备事件认证器。
- 没有权重、可重建权重 payload、npz、canonical raw/reference 数组、生成模型、二进制、系统环境清单或进程日志。没有提供大包的编码、重命名或替代副本。
- 没有改变既有 metadata/用户公开许可问题；没有改动原资产和源目录。

`INSTALL_MAP.json` 记录候选安装映射，不构成运行通过证据。实际安装或发布状态以仓库 Git 提交及远端核验为准。
