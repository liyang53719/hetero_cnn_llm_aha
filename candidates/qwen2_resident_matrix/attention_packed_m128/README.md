# M128 原始 packed owner 分块调度（准备中）

单独覆盖原始 PackedSchedule.run，保持原始 owner/client/物理读写协议。每个 QK group 处理不超过16个连续key，8个深度步、相同16项折叠与BF16/scale边界；score ACK后才释放结果。softmax按每个head原key顺序遍历所有行，最后才除法。PV保持同一query/KV组的6个head，按key递增，且每16key串行重载6条概率行，保持同一个未完成Matrix group。

scratch score4096..4143、weight4144..4191，原始同一个Banks/ACK机制与显式384B panel资源不变。完整原始Public profile仍只接收M16；M128类型、observer捕获点、资产、全程序入口尚未接通。

已完成：3项 normal/-O 控制测试。当前测试只使用显式零值控制回调，核对M1/M2/M16事件投影、M17/M32尾块、M128完整96条scratch行和债务计数；不能视为算术等价。待办：独立复审、真实原始owner小样本数值、M16成功后再评审M128数值预算。无RTL、全周期利用率或80/90%声明。

M128预期QK55296步/PV16512步，共71808；QK6912组/PV256组；scratch读写27648次。计数不是硬件周期，输入DDR、Scalar、held-result和bank等待仍须计入。
