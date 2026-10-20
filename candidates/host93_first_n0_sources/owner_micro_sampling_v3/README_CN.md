# 原 QwenOwnerKernel 局部合法刺激源码

状态：本 v3 为 SOURCE_ONLY_NOT_EXECUTED。原 v2 已有独立 cache actual 失败证据；本后继只改观察调度与纯冷测，尚未编译或运行。

## 范围和真实计算

从冻结76,366,612B / 2fcc1ba70ad3406b967292624329593aa38e3fe562e9ff3ac675eec100562f61的SV直接选QwenOwnerKernel；它就是Host选中的唯一无参数module。保真实Router→Coordinator→Dense/Banks→ScheduledSiluOwner→Matrix/FMA，不改内部状态。M128/N1536/K1536、mask255、1024/512两个K范围、pairReverse全部原样。N0完整FP32 786432B、Wq完整BF16 4718592B由大小/SHA固定，并从同一读取buffer按原字节地址服务；不重算N0、不抽样、不给Matrix脚本终端、不改偏置/舍入。

这是一份owner集成微刺激。外部typed RAM代替该模块外面的Host/iDMA/AXI链。尚未继承N0执行前史，不把typed写响应叫AXI B或ACK1，不授full-block、官方raw、application或typed对RTL数值通过。

## 固定接线

生产清单恰7件：owner_micro.cpp、owner_inputs.inc、owner_observations.inc、owner_readonly.vlt、sha256.hpp、PORTS.json、OBSERVATIONS.json。SHA头逐byte继承原PC01桥，非新算法。PORTS精确196条（150输入/46输出，包括clock/reset），job为30字段加ready/valid。95只读scalar观察均带源module/var和1..64位宽；caller必须在新生成头内逐名/宽唯一核实后才编译，不能仅相信预计成员名。

四个原VLT保留，再附本片owner_readonly.vlt；不新增通用warning忽略。所有输入显式初始化，只有顶层输入被赋值，内部root仅读。

prefixWorkspace不是未使用输入：valid=1，base4507654464，extent786432，epoch7对应generation8；内部splitK已由原SV固定2560，没有顶层splitK可驱动。job仍原tag458753、identity由router算458754；无关job payload保持原零，不混入workspace generation。

## RAM与窗口退休

RAM保持原adapter的单一全局外存事务、burst优先于writeRequest；普通memory.valid在本QKV路径不应出现，出现即诊断失败，不用零值或伪ACK补齐。burst是原固定单64B，读取真实N0或Wq payload并完整echo tag，last=1。Wq reservation尾部不可读。响应有效不依赖ready，停顿时数据/tag稳定。

本目标发生于第二窗口开始，只有ng0写回会出现：128行按原地址每行一个10拍descriptor，LAST仅末拍；全部640B实际写入并覆盖检查后才给typed写响应。输出仅保私有内存，不落数组。每个请求/响应只在稳定低沿采样的valid&&ready对应高沿退休。

目标要求四次精确window请求，三次成功partial终端，正确physical issue/done、lease/slot/K范围/producedBeats；经ng0真实Vector求和和drain完成128个typed写响应/81920B后，再见ng160 partial1真实首issue。wide12801/slice102408只是额外核对，不独立代替这些事件。

停止时可能仍有live job和外存债务，这正是局部边界停止；job_completed始终false，没有full job terminal/ACK1完成声明。resetRequired、runtime error或任何协议异常优先保存有界诊断。v3 保留 raw high 诊断；runtime fatal 立即拒绝，原采样事务校验/结算后在完整低沿 settle 检查 reset。失败若发生在结算之前，账本仍截至前沿；若发生在 LOW_POST_EDGE_SETTLED，账本包括本高沿。两种样本标签明确区分。

## 调用和有界输出

CLI仅两个私有绝对文件路径：固定N0、固定Wq。逐组件无symlink打开、完整regular size/hash、前后fd/name身份稳定，同buffer供数。没有公开机器路径常量。

上限为复位后500000周期；v3 后继调用拟复用已固定 owner archive/runtime，以外层同540秒窗口（driver编译120、链接60、运行300、落证60），单CPU、AS6GiB。源准备与冷测不使用该native预算。任何阶段资源不足/超时保INCOMPLETE，不能自动加窗，也不承诺一定到目标。

stdout是同一OWNER_MICRO_V1 schema的scalar JSONL：READY一条，每32768周期最多15条PROGRESS，最后一条终端，总最多17条。每条低于32KiB；不输出数组、私有文件路径、原始异常文本。自然0仅表示TARGET_BOUNDARY_OBSERVED；1表示CONTRACT_FAILURE；2表示INPUT_ERROR/INCOMPLETE/输出失败。hard timeout以caller的原阶段资格与已落progress为准。完整字段和固定值在CONTRACT.json。

## 冷测限定

cold_entry.py先固定生产manifest和test hash，读取每件一次，核size/SHA后仅用已核buffer编译运行Python纯mock/source检查；不调用Verilator、g++、make、Host、Torch或NumPy。93个原件/协议/调度测试加8个loader替换/截断/symlink等负例，普通/-O和搬迁四种模式的实际结果见COLD_RESULTS.json。它们不执行C++，更不是RTL重现。真正C++语法/生成字段/计算执行资格仍必须由后续有界三阶段与独审取得。

路线可行性先审身份见CONTRACT.json；本片SOURCE独审身份尚待。历史PC01上游根因仍UNKNOWN。

## v2唯一生产修正

v1保留。F01只将catch(Failure)的原exit先固定，终端report发生secondary异常时仍返回原code；verified契约失败保持1，输入失败保持2。原RAM、真实退休条件、模型、预算、观察和输入均不变。两个纯mock/source用例覆盖该双故障。

## v3：响应退休后的观察调度后继（SOURCE，实际未运行）

原 v2 与 session44110 FAIL 原件保留。本后继仅在 main 调度与同记录诊断中区分 raw high 和完整低沿 settle：原 low fires 不变，原 Progress/RAM 校验与退休各一次，runtime fatal 仍立即拒绝。先保留高沿后的 95 字段快照/reset 值，再结算已采样事务；clock=0 驱动 producer 新值、eval/priority/eval 后检查完整 resetRequired/runtime 门，且门先于任何下一上升沿。原标签 HIGH_EVAL_POST_SOFTWARE_PREVIOUS_EDGE 仅用于尚未成功结算的异常；新 LOW_POST_EDGE_SETTLED_SOFTWARE_RETIRED 软件账本包括本高沿。raw_high_before_settle 是同记录诊断，不能单独授予 RTL 故障或成功。

原 RAM/tag/LAST/data、输入同 buffer、工作区、K ranges、M128、窗口/退休/物理计数、500000 周期与全部资格门不改；其余六生产文件逐字不变，不需新增 VLT 或观察字段。不写内部状态、不清 reset、不以撤 valid 后清除单独推定刺激违约。合法 Decoupled valid 可以保持至下一低沿；旧失败与消费者已更新而外部服务未更新的半步观察解释相容；实际缺叶使该因果尚未确定。现有 actual 95 字段缺 writeState/rawAck/drainPoison 直接值，静态归因仍须保留该观测局限。

纯冷测试验证调度顺序及持续错误、bad tag/error、重复响应、stall、原事务错误和 runtime fatal 仍拒绝；它们不是新 RTL 执行。原 actual 仅证明运行到 ng0 首 drain 的 RESET_REQUIRED_HIGH，不等同原 Host ng160 根因。

## 本次独立 SOURCE 审核

正式 SOURCE 已获有限 GO：review_owner_micro_core_v3_20261019T2356，MANIFEST 1181 B / 6b109cd2f3b65e6f0b57327966f595f4703edf9b5c05f8518d27c58a7a8430ec；SUMMARY.md 4658 B / 947fb90d4aeae27c3b727efab7ea4b2784a0b367201a5453363da2af8e7aecf3；verdict GO_OWNER_MICRO_V3_FALLING_LOW_SETTLE_SOURCE_ONLY。独立核28成员/17来源、93+93冷测及26+26原式诊断；只授本片SOURCE，原actual缺叶的局限仍保留。当前 v3 编译/native/RTL 为 NOT_EXECUTED。现有 93 主测+8 loader 在普通/-O/搬迁四模式通过，仅为纯 mock/source 测试；原 v2 actual FAIL 保留。
