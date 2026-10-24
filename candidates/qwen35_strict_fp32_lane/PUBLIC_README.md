# Strict FP32 单 lane 源码与软件参考摘录

已完成一次有界纯 Python 控制：18 组、20 个定向向量、256 个固定种子 finite triples，自然退出 0。整数 significand 模型与独立 Fraction 邻值参考一致；这不是 Scala、HardFloat 或真实握手的运行结果。具体范围及收据指纹见 TEST_SCOPE.json。

新源仅单 lane，共享一个 full32 Pre 与原 Mul/Post/Round；严格模式先 Mul 舍入，再 Add 舍入，失败不提交。原 BF16、主阵列、公共入口均未修改。原始 README/SCOPE/向量中的待运行文字按冻结字节保留，当前软件控制结果由独立 TEST_SCOPE 说明。

必须保留的未来集成阻断：minnormal 边界的 HardFloat UF|NX=3 与旧 CPP 修正 NX=1 不同，软件通过不消除此差异；BF16 特殊值只是注入响应传播，不证明 NaN payload。无硬件数值、16 词组、面积/Fmax 或 80% 利用率资格。

本摘录保留 12 个原文件字节，含原 SOURCE_MANIFEST，但不发布机器 TEST_COMMAND、原始日志/收据、工具、class、IR、权重或数组。因此它不是可直接运行的完整包；原 tests 的严格 pin 门仍需完整原包和 INPUT_PINS 指向的小源码，不提供改 pin 或绕过缺项的运行器。目标环境为 CPython 3.12，隔离选项为 -I -S -B。未在本公开摘录上重跑测试。
