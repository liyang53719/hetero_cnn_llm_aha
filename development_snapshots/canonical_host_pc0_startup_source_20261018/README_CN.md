# 启动与 PC0 项目源码安全小 checkpoint 候选

这是待独立复核、未提交及未发布的 SOURCE-only 保存候选。只保留启动和 PC0 的项目 harness / 观察适配源码、纯 Python 文本冷测以及人工整理的失败摘要。本包不是独立可编译模型，不是新的运行结果，也不提供数值、协议、综合、QoR 或 full-block PASS。

## 实际结论必须保留

原 PC0 尝试在 300 秒工作预算边界被中断，结论为 NOT_COMPLETED。最后保存的周期采样为 598016，PC=0，issued_jobs=1，write_bytes=0；最后采样不是中断时的精确最终周期。没有 PC0 成功凭证、实际 N0 输出文件或两参考数值比较结果。

write_bytes 是已完成 owner 结果的累计量。它不是逐 B 事务计数，因此 0 不能证明无首 B、无部分写回或写通路停滞。保存记录不能还原中断时的 token、归约状态、真实 B 数、已提交字节数或最终内部状态，也不能据此判定死锁、OOM 或数值错误。

只读源分析给出的正常 M128 归约下界为 2428928 周期；更弱独立下界为 2018304。两者都超过源码保留的 2000000 周期 cap。前者由每行 1536 项、1536 次乘调用、1672 次加调用、每项局部读 3 周期、正常标量调用 4 周期及非调用控制周期计得：每行 18976 周期，乘 128 行。该下界尚未计入输入搬运、gamma、写回、除法/开方和 Host 开销，不能当上界、实测延时、墙钟预测或本次内部进度证据。测试只复算已审诊断的公式，不重新证明外部 RTL 状态机。

旧 cap 原样保留以保存真实失败对应源码；本候选没有扩时、改 cap 或重跑。已结束进程没有可续跑的寄存器/RAM checkpoint。进一步运行需要独立源码修订及审批，并从 reset 与完整输入重新开始。

## 14 个 payload 文件

- startup/startup_main.cpp、startup/startup_inputs.hpp、startup/startup_ledger.hpp、startup/dpi_forwarders.hpp：20 步固定 no-job 启动、真实八 leaf DPI 生命周期与 reset 观察。
- pc0/pc0_main.cpp、pc0/startup_inputs.hpp、pc0/startup_ledger.hpp、pc0/dpi_forwarders.hpp：保留固定 PC0、唯一低/高沿工作调度、真实 ACK0 后立即停止及有界工作期 DPI 观察。
- pc0/n0_participant.hpp、pc0/resident_participant.hpp、pc0/shared_edge_runtime.hpp：保留同一 HostMemory、真实成功 B 后退休、ACK 后发布和统一调度的源码。完整 Host / 其他 owner / prefix / 全域闭合仍 fail closed。
- failure_summary.json：人工整理的有限事实与资格边界，既非原 receipt，也非新的实际运行证据。
- test_source_only.py：只读包内文本和内存负例的 Python 标准库测试。
- README_CN.md：本说明。

两个目录的 forwarders 和 inputs 相同，刻意各保留一份，使原各自 ledger 的 include 解析关系清晰。forwarders 是项目 DPI 转发适配源码，不包含生成模型实现。

## 来源、变换和隐私边界

11 个源码文件中，5 个与原源码逐字一致，6 个仅将共 9 行跨项目快照 include 投影为相对逻辑文件名。发生投影的为两个目录中的 dpi_forwarders.hpp、startup_inputs.hpp，以及 pc0/n0_participant.hpp、pc0/resident_participant.hpp；这些文件明确为 DERIVED_INCLUDE_RELOCATION_ONLY。其他源码为 RAW_IDENTICAL。没有额外文本或行为修改。

每个文件的字节数、SHA-256、准确逐行反投影及原源映射由独立 controls 保留，controls 不属于默认公开 payload。包内测试固定投影后源码 hash；逐行反投影在私有 controls 核验，不能仅凭包内测试声称已独立验证原来源。hash 不是签名，文本谓词不是 C++ 语义证明。

不附原运行 receipt/raw log、实际内存地址、环境绝对路径、工具清单、环境元数据、原诊断全文、权重/输入字节、参考输出、生成 SV/模型 C++、类文件、对象、库或可执行文件。保留源码中的抽象指针/字段名和运行时 handle 格式化逻辑，不附任何实际运行的 handle 数值。源码现存输入流摘要是固定逻辑内容身份，不是输入数据。此前单独候选中的 axi_service、host_fields、n0_fields 等 payload 不在本包重发。

## 明确未附的依赖

直接 quoted include 尚缺 VHostBlockTop.h、VHostBlockTop___024root.h、VHostBlockTop__Dpi.h、svdpi.h、n0_fields.hpp、axi_service.hpp、sink_stream_bridge.hpp、host_fields.hpp。它们还依赖实际模型/runtime、Host ABI、HostMemory、loader、原 observer、转发链接设置及其他递归依赖。这里不建立递归构建闭包，不附安装位置或工具版本，不用替代模型、常量事件或占位类型伪造闭合。

## 隔离冷测

只复制 payload 到一个空目录，在该目录执行：

    python3 -I -S -B test_source_only.py
    python3 -I -S -B -O test_source_only.py

测试只读取自身 payload 文本：准确文件集合、源码字节/hash、include 边界、启动/PC0 关键文本契约、失败摘要及内存篡改负例。它没有网络、子进程、编译器或模型导入接口。正常模式与优化模式都必须通过。不会生成或运行 C++、Host、RTL、EDA、native 模型，也不会加载权重或 actual 输出。通过冷测只说明本候选的有限文本完整性及回归谓词成立。
