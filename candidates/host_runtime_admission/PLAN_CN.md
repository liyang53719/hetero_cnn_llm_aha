# 共同原 Top 冷 M128 准入候选

**TEMP / INCOMPLETE：这是源代码、小模型与单源实际 Scala 编译通过，不是五模型完整支持。完整 M128 数值验收 0/5，同 RTL 验收 0/5。**

## 本批实际改变

原 `HostBlockCommandsV4` 精确五处编辑：已知 profiles1..4 只有在原 official BF16 构造、retained Matrix、matrixColumns=256、resident FFN、production Down 与全部 runtime QKNorm/RoPE/KV/GQA/output 服务共同存在时准入；不使用测试 force、新 wrapper 或按模型硬件定义。profile0 原21条命令、FP32存储、数值操作与原完成提交逻辑不变。

Host header 不含 token 数，故 launch 准入自身不证明 M128：实际 typed inputNorm 将 runtime rows 限定为128，并保持冷启动、generation0、未提交 checkpoint、只读真实输入及生产者依赖。carried checkpoint 仍不支持。后续真实物理ACK、排空与最终原子完成门均未删改。

原 GDN M128 scratch 的 rank2 `[heads,419840]` 单维超过 SHAPE4 的18bit。现改为 rank3 `[heads,128,3280]`，element strides `[419840,3280,1]` 均满足23bit无符号范围；每 head 仍为1,679,360字节，heads为16或32。既有 kernel/owner 地址、物理布局和容量不变；M16原rank2分支保留，但本共同入口只允许M128。

## 已完成的精确验证

- 单一实际 Commands 源在997个冻结 baseline classes上编译，native exit0、空编译日志、3,790项前后pin相同，产生4类 / 1,164,032字节；不是31源重编。
- 最终31源 / 159类＝本次1源4类＋30继承源155类。公开包仅带该1源，另25源引用真实已发布文本，5源仍 requires-parent。
- 本包 `check_common_admission.py`：328个有限布尔/整数case、14类源码删除负例；`check_delta.py`：精确五处逆变换及16,384个独立能力/profile/checkpoint组合。均只做源与模型检查，不运行Chisel/DUT。
- `verify_package.py`核文本清单，`verify_summary.py`核本包摘要约束；均不重现编译或硬件结果。运行以上四个脚本各一次普通Python及 `python3 -O`。delta检查需要相邻已发布 `host_runtime_fence` 的精确 Commands 源。

发布独审发现原检查器盲点：在安装条件末尾附加 `|| true` 可躲过前缀snippet检查，早版逆变换又把整个新增区移除；16,384个真值表case只是抽象模型，不能单独证明该源码表达式。精确文件hash检查始终拒绝篡改。本公开版在逆变换前逐字校验两个完整新增区，同时收紧安装表达式边界；保留原检查器和失败探针的hash与历史，不改已编译Scala，不重跑编译。

## 不得继承的历史结论

先前封闭launch seal构造的 originalTop high→official-low结构PASS仅属于旧源码。**本次改变Commands可达性与scratch ABI后，该结构PASS不继承；新结构测试尚未运行。** 原RawPrep构造失败、GQA组合环失败、修复后结构PASS及30条宽度警告都留在旧包，不抹除，也不将历史警告视为已清零。

本批未执行完整程序、原非DPI后端、RTL或数值仿真。五份完整typed程序/生成器仍属另一个工作项，未随本包上传；QKNorm生成器契约核对不作为本批数值通过证据。MoE tie契约仍待结论。

## 下一门及资源边界

重新验证同一原Top结构，完成五份真实输入/权重/状态/scratch程序与独立参考，再以真实共享Matrix/Scalar/iDMA后端执行完整M128及同刺激RTL验收。不得灌入中间结果或expert IDs替代实际计算。

源差分未增加FPU、Matrix、数值缓存或Host接口位；现有4096逻辑MAC与32lane共享bank定义不变，但准入比较和解码逻辑改变，不能宣称零面积、PPA或利用率提升。旧整Top的81 ALU/17 Scalar统计不是本次新测量。

`REPRODUCTION.json`只给脱敏精确命令模板、pin和限额；仍需父级完整类/源/工具闭包及严格监督器，不是fresh-checkout独立复现。历史传递图不完整，不把缺失档案说成PASS。仅上传源、脚本、hash和摘要；无权重、npz、二进制、IR/RTL或私有机器路径。
