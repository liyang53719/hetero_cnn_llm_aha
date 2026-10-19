# 原 QwenOwnerKernel 局部合法刺激源码

状态：SOURCE_ONLY_NOT_EXECUTED。本片只准备C++驱动、只读观察配置与纯合成冷测，尚未生成、编译或运行该RTL top。

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

停止时可能仍有live job和外存债务，这正是局部边界停止；job_completed始终false，没有full job terminal/ACK1完成声明。resetRequired、runtime error或任何协议异常优先保存有界诊断。已结算high之后先检查真实失败，再事务性提交软件账本，失败样本明确标为软件截至前沿；不会把当前RTL组合量与旧账本冒成同拍退休。

## 调用和有界输出

CLI仅两个私有绝对文件路径：固定N0、固定Wq。逐组件无symlink打开、完整regular size/hash、前后fd/name身份稳定，同buffer供数。没有公开机器路径常量。

上限为复位后500000周期；实际调用使用外层同1320秒窗口（生成360、编译600、运行300、落证60），单CPU、AS6GiB。源准备与冷测不使用该native预算。任何阶段资源不足/超时保INCOMPLETE，不能自动加窗，也不承诺一定到目标。

stdout是同一OWNER_MICRO_V1 schema的scalar JSONL：READY一条，每32768周期最多15条PROGRESS，最后一条终端，总最多17条。每条低于32KiB；不输出数组、私有文件路径、原始异常文本。自然0仅表示TARGET_BOUNDARY_OBSERVED；1表示CONTRACT_FAILURE；2表示INPUT_ERROR/INCOMPLETE/输出失败。hard timeout以caller的原阶段资格与已落progress为准。完整字段和固定值在CONTRACT.json。

## 冷测限定

cold_entry.py先固定生产manifest和test hash，读取每件一次，核size/SHA后仅用已核buffer编译运行Python纯mock/source检查；不调用Verilator、g++、make、Host、Torch或NumPy。74个原件/协议测试加8个loader替换/截断/symlink等负例，普通/-O和搬迁四种模式的实际结果见COLD_RESULTS.json。它们不执行C++，更不是RTL重现。真正C++语法/生成字段/计算执行资格仍必须由后续有界三阶段与独审取得。

路线可行性先审身份见CONTRACT.json；本片SOURCE独审身份尚待。历史PC01上游根因仍UNKNOWN。

## v2唯一生产修正

v1保留。F01只将catch(Failure)的原exit先固定，终端report发生secondary异常时仍返回原code；verified契约失败保持1，输入失败保持2。原RAM、真实退休条件、模型、预算、观察和输入均不变。两个纯mock/source用例覆盖该双故障。

## 正式独审与本次安全发布

上述README按源码冻结时点原样保留。当前独审已给GO_OWNER_MICRO_CORE_F01_CLOSED_SOURCE_ONLY：review_owner_micro_core_v2_20261019T2306，MANIFEST752 B / 483a3b9cea73de582cb72ba7bb26848d9a4d50b202a3501066270a29ad257d00；SUMMARY1679 B / 09504038c750d4fb6a50263a0647a7c48b219cb8cd61136a9659303b3fdac01d。26成员/17来源闭合，唯一F01逆投影成立，其余6生产原样；作者四模式各74+8纯合成通过，独立74+74通过。

本批公开14个原件、该README后缀和安全STATUS，以及中文计划完整replacement。源码/测试原件不改，没有私有绝对机器路径、输入内容、数组或二进制。实际生成/编译/RTL运行仍NOT_EXECUTED；新top实际ABI及95生成字段需caller后验，SOURCE GO不能代替该门。原PC01失败与上游UNKNOWN保留。

本批不触发新的Host/RTL/native作业；workflow文件不变，普通push轻量guard另记。
