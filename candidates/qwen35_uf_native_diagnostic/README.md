# UF 边界：原 C++ 软件实测摘录

本包保存五份原字节源码/刺激和安全摘要，不是完整可执行闭包。原 vector16.cpp、Fraction 参考已存在，故不重复复制；完整环境计划、工具二进制、头文件全集、共享库、原始日志和私有收据不发布。

实测 24 个有限单 lane 输入和 3 个原 mask30 batch。正负 minnormal 中点交付值相同，但原 CPP 返回 NX=1，独立同式 raw-host 操作返回 UF|NX=3，与 HardFloat 源规范预测 3 一致。原 mask30 实际继续 Add；小到零和溢出对照实际止于 Mul。这个结果确认旧 CPP flags 策略差异，不能解除未来集成阻断。

raw probe 是独立执行，不是原函数内部观测。HardFloat 数值硬件、RTL、16 lane、主阵列和完整模型均未测试。所有旧源及证据不改。

原入口 launch_native.py 保留严格固定计划 pins；本公开包故意省略机器绑定 FROZEN_PLAN.json，不能直接运行。复现需单独构建并审定固定环境计划，保持原七个编译 flags、真实两 TU 的 -M 预 pin 子集检查、三阶段自然退出和清理门。不得将缺失计划当理由绕过原门。

STIMULI.json 保留发布前冻结时的静态标签及预测字段；实际结论见 SUMMARY.json，二者职责不同。

本包无权重、数组、运行流、ADMISSION、机器目录或原始工具清单。REPRODUCTION_PINS.json 只提供必要源/环境/结果指纹，不能替代实际依赖闭包。
