# 隔离 finite Mul UF 软件修复

只发布新 C++ 副本、精确修复与驱动差分、固定刺激和限定摘要。旧 vector16.cpp、模型、原实际诊断及所有旧证据不改。

算法用 uint64 精确乘积比较 T=(2^25−1)·2^-151。等号不tiny；完整指数不直接移位，只有bit-length相等分支进行至多48位对齐。UF仍与原操作 FE_INEXACT 相与，不能用最终零/normal结果或raw host UF代替。

实测70个有限输入与5个原API batch。新副本全部交付值/flags与独立Fraction和固定HardFloat源规范一致。正负minnormal边界现在flags3并止于Mul；阈值恰等及精确subnormal仍成功Add。旧原函数只具有先前24例实测，新增46例的旧列是源规则预测，未重跑旧ELF。

R1是未执行的源码HOLD，不是实际FAIL；R2恢复NX短路。R1_TO_R2.patch仅解释该最小修正。vector16_tininess.patch从原CPP得到最终R2副本。其余三patch均以先前原软件诊断公开源码为baseline，不应依次套到R1。逐字结果pins见REPRODUCTION_PINS.json。

完整运行仍需要单独冻结的环境计划和既有监督闭包。本摘录不包含机器计划、工具表/二进制、原始日志、共享库、ADMISSION或权重，不能直接运行。必须保留原60秒共享监督和依赖子集/源hash/清理门，不能绕过省略的固定计划。

本次真实运行的是C++软件，不是HardFloat硬件、RTL或lane握手。源规范的一致并不解除未来硬件/整模集成阻断，也不宣称阵列面积、利用率或性能。
