# Host binding / resident / N0 项目源码安全候选

## 资格与边界

这是独立的 SOURCE-only 保存候选，尚未提交、上传或发布。只保存已审三份项目观察/适配源码中的 8 个头文件和本包说明、来源映射、静态测试及 manifest。此包不是独立可编译闭包，也不是编译、运行、RTL、数值或 full-block PASS 的证据。

原三份审查均只授予有限 SOURCE 资格。其准确 source snapshot、source manifest SHA-256 和 review manifest SHA-256 在 SOURCE_MAP.json。审查身份属于原冻结源码，不等于本候选已获独立审查。原资产未修改。上游 codegen 的 FAIL_HOST_TOP_CODEGEN / 单项 UNOPTFLAT 历史没有因本包改变。

## 保留内容

- generated_binding.hpp：项目字段绑定适配器，保留真实模型/成员名、只读注册检查、468 个 pre 与 13 个 post 字段读取及粘性失败。它是项目生成器产生的适配源码，不是 Verilator 生成的模型实现；本包不包含生成模型 C++ 或 SV。
- host_fields.hpp、silu_edge_runtime.hpp：83 个公开引用身份检查、54 个输入元素快照和低/高沿采样源码。
- resident_evidence.hpp、physical_observer_bridge.hpp：实际 resident/shared-loan 七类计数、先原 observer post 验证再记账、子域 checkpoint；完整 PhysicalObserver 11 方法仍未闭合，缺失域继续 fatal。
- n0_fields.hpp、n0_physical_memory.hpp、axi_service.hpp：实际 retained 字段读取、N0/PC0 的同一原 HostMemory 接入、真实成功 B 退休后 SSA 写入、private nested loader sink 与 completion ACK 后 N0 发布源码。其他 owner、prefix 和完整 Host admission 继续 fatal。

保留实际层次/字段名是为了保留项目行为和来源可核性。这里没有替换成模拟字段、常量事件或参考数值，也没有新增第二份 RAM。

## 逐字来源和唯一变换

8 头中 silu_edge_runtime.hpp 与原文件逐字相同，其余 7 头只对 10 行跨快照 include 做逻辑文件名重定位。SOURCE_MAP.json 的每项都有原字节数、原 SHA-256、当前字节数、当前 SHA-256、模式及精确行号/前后内容。

DERIVED_INCLUDE_RELOCATION_ONLY 表示派生源码，绝不声称原字节。RAW_IDENTICAL 才表示逐字相同。逆向按行恢复 include 后必须得到原 SHA-256；未列出的任何字节都不允许变化。原文件 SHA-256 已在本地逐项对原冻结 manifest 核验。包内反投影可离线重复，但不能代替独立取得原冻结源后的来源验证，亦不认证任何编译后对象或二进制。

没有打包原完整 pins、实际字段证据表、原 review 报告、实际 receipt、运行日志、系统路径、工具链清单、权重、输入数据、生成模型 C++/SV、对象文件或可执行文件。SOURCE_MAP.json 只有源身份和最小 include 变换，不携带这些外部资产内容。

## 外部依赖明确未附

本包只列直接 quoted include 的逻辑文件名，不列工具安装位置或版本。官方 Verilator 类型头、实际模型头、原 silu_observer、Host ABI、HostMemory 与 loader bridge 均未附；递归依赖、编译参数和完整来源闭包也未重建。读者必须另行通过受审依赖门取得它们，不能用占位类型或替代模型把本候选变成“可编译通过”。

include 重定位不会自动建立正确搜索路径，因此不得据此宣称已经具备可复现 C++ 构建。保留适配器源与恢复其原字节是本候选的可复核范围。resident 与 N0 分片也不能各自对同一模型重复 eval；统一调度仍是后续集成门。

## 只读冷检查

将 payload 中 12 个文件放在一个空目录，使用 Python 标准库执行：

    python3 -I -S -B test_source_only.py
    python3 -I -S -B -O test_source_only.py

测试只读包内 UTF-8 文本，校验准确文件集合、manifest hash、逐字/派生来源、10 行 include 反投影、外部依赖边界和有限关键源码谓词，并做内存中篡改负例。不读原生成模型、不加载权重、不运行旧原始测试、不执行编译器、链接器、HDL、EDA、Host、模型或 C++ 对象。测试没有网络或子进程接口，也不写生成文件。

源码谓词是对冻结文本的有限回归保护，不是 C++ 语义证明、协议模型检查或 actual trace。manifest 哈希也不是签名或独立可信证明。未来任何编译/运行资格、全 17 owner / 21 completion / 27 capture、prefix 生命周期、全域活动冻结及数值比较仍要独立完成。
